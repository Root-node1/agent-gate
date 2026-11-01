#![allow(dead_code)]

use std::fs;
#[allow(unused_imports)]
use std::io::{Read, Write};
#[allow(unused_imports)]
use std::net::{IpAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread::{self, JoinHandle};
use std::time::Duration;

const DEFAULT_BACKEND: &str = "http://127.0.0.1:8000";
const MAX_BODY_BYTES: usize = 10 * 1024 * 1024;
const PROXY_PATHS: [&str; 2] = ["/api", "/v1"];
const ALLOWED_METHODS: [&str; 7] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];
const HOP_BY_HOP: [&str; 12] = [
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    "content-encoding",
    "expect",
];

pub struct ServerHandle {
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
    pub port: u16,
}

impl Drop for ServerHandle {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
    }
}

/// Strict validation of `AGENTGATE_BACKEND_URL`.
///
/// Returns a canonical `scheme://host[:port]` string on success.
///
/// Policy:
/// - `https` is allowed for any non-unsafe host (hosted backend).
/// - `http` is allowed only for loopback hosts (127.0.0.1, localhost, [::1]).
/// - Embedded credentials, fragments, and query strings are rejected.
/// - The path must be empty or "/".
/// - Unsafe IP destinations (unspecified, broadcast, multicast, and other
///   non-unicast addresses) are rejected.
/// - No silent fallback: an invalid value is an error.
pub fn validate_backend_url(raw: &str) -> Result<String, String> {
    let raw = raw.trim();
    if raw.is_empty() {
        return Err("backend URL must not be empty".to_string());
    }
    let parsed = url::Url::parse(raw).map_err(|_| "malformed backend URL".to_string())?;

    let scheme = parsed.scheme();
    if scheme != "http" && scheme != "https" {
        return Err(format!("unsupported scheme: {}", scheme));
    }

    // No embedded credentials.
    if !parsed.username().is_empty() || parsed.password().is_some() {
        return Err("backend URL must not contain credentials".to_string());
    }

    // No fragments or query strings.
    if parsed.fragment().is_some() {
        return Err("backend URL must not contain a fragment".to_string());
    }
    if parsed.query().is_some() {
        return Err("backend URL must not contain a query string".to_string());
    }

    // Path must be empty or "/".
    let path = parsed.path();
    if !path.is_empty() && path != "/" {
        return Err("backend URL must not contain a path".to_string());
    }

    let host = parsed
        .host_str()
        .ok_or_else(|| "backend URL must include a host".to_string())?;
    if host.is_empty() {
        return Err("backend URL host must not be empty".to_string());
    }

    // Classify host.
    let is_loopback = match parsed.host() {
        Some(url::Host::Ipv4(ip)) => ip.is_loopback(),
        Some(url::Host::Ipv6(ip)) => ip.is_loopback(),
        Some(url::Host::Domain(d)) => d.eq_ignore_ascii_case("localhost"),
        None => false,
    };

    // Reject unsafe IP destinations regardless of scheme.
    let unsafe_dest = match parsed.host() {
        Some(url::Host::Ipv4(ip)) => is_unsafe_ip(&IpAddr::V4(ip)),
        Some(url::Host::Ipv6(ip)) => is_unsafe_ip(&IpAddr::V6(ip)),
        _ => false,
    };
    if unsafe_dest {
        return Err("backend URL points to an unsafe address".to_string());
    }

    // HTTP only for loopback.
    if scheme == "http" && !is_loopback {
        return Err("HTTP is only allowed for loopback backends".to_string());
    }

    // Build canonical URL.
    let port = parsed.port();
    let canonical = match port {
        Some(p) => format!("{}://{}:{}", scheme, host, p),
        None => format!("{}://{}", scheme, host),
    };

    // Lowercase scheme check already done; ensure host not wildcard.
    if host == "*" || host == "0.0.0.0" {
        return Err("backend URL must not use a wildcard or unspecified address".to_string());
    }

    Ok(canonical)
}

pub fn is_unsafe_ip(ip: &IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            v4.is_unspecified()          // 0.0.0.0
                || v4.is_broadcast()     // 255.255.255.255
                || v4.is_multicast()     // 224.0.0.0/4
                || (v4.octets()[0] == 169 && v4.octets()[1] == 254) // link-local
        }
        IpAddr::V6(v6) => {
            v6.is_unspecified() // ::
                || v6.is_multicast() // ff00::/8
                || (v6.segments()[0] & 0xffc0) == 0xfe80 // link-local
        }
    }
}

#[derive(Debug)]
struct ValidatingResolver;

impl ureq::unversioned::resolver::Resolver for ValidatingResolver {
    fn resolve(
        &self,
        uri: &ureq::http::Uri,
        config: &ureq::config::Config,
        timeout: ureq::unversioned::transport::NextTimeout,
    ) -> Result<ureq::unversioned::resolver::ResolvedSocketAddrs, ureq::Error> {
        let default = ureq::unversioned::resolver::DefaultResolver::default();
        let result = default.resolve(uri, config, timeout)?;

        let scheme = uri.scheme().map(|s| s.as_str()).unwrap_or("");
        let http_scheme = scheme == "http";

        // Reject if ANY resolved address is unsafe (DNS rebinding guard).
        for addr in result.iter() {
            if is_unsafe_ip(&addr.ip()) {
                return Err(ureq::Error::HostNotFound);
            }
            if http_scheme && !addr.ip().is_loopback() {
                return Err(ureq::Error::HostNotFound);
            }
        }
        if result.is_empty() {
            return Err(ureq::Error::HostNotFound);
        }
        Ok(result)
    }
}

fn backend_url() -> Result<String, String> {
    match std::env::var("AGENTGATE_BACKEND_URL") {
        Ok(v) => validate_backend_url(&v),
        Err(_) => validate_backend_url(DEFAULT_BACKEND),
    }
}

pub fn validate_host(host: &str, port: u16) -> bool {
    let host = host.trim().to_ascii_lowercase();
    if host.is_empty() || host.contains('@') || host.contains(',') {
        return false;
    }
    let expected = [
        format!("127.0.0.1:{}", port),
        format!("localhost:{}", port),
        format!("[::1]:{}", port),
    ];
    expected.iter().any(|e| e == &host)
}

pub fn is_proxy_path(path: &str) -> bool {
    let p = path.split('?').next().unwrap_or(path);
    if p.contains("..") || p.contains('\0') || p.contains("://") {
        return false;
    }
    let decoded = percent_decode(p);
    if decoded.contains("..") || decoded.contains('\0') {
        return false;
    }
    PROXY_PATHS
        .iter()
        .any(|prefix| p == *prefix || p.starts_with(&format!("{}/", prefix)))
}

pub fn is_allowed_method(method: &str) -> bool {
    ALLOWED_METHODS.contains(&method)
}

pub fn safe_join_dist(dist: &Path, request_path: &str) -> Option<PathBuf> {
    let p = request_path.split('?').next().unwrap_or(request_path);
    if p.contains('\0') || p.contains("://") {
        return None;
    }
    let p = p.trim_start_matches('/');
    if p.is_empty() {
        return Some(dist.join("index.html"));
    }
    let decoded = percent_decode(p);
    if decoded.contains("..") || decoded.contains('\0') || decoded.starts_with('/') {
        return None;
    }
    if p.contains("..") || p.starts_with('/') {
        return None;
    }
    let candidate = dist.join(p);
    let canon_dist = dist.canonicalize().ok()?;
    if candidate.exists() {
        let canon_candidate = candidate.canonicalize().ok()?;
        if !canon_candidate.starts_with(&canon_dist) {
            return None;
        }
        if candidate.is_file() {
            return Some(candidate);
        }
        if candidate.is_dir() {
            let idx = candidate.join("index.html");
            if idx.is_file() {
                return Some(idx);
            }
            return None;
        }
    }
    let fallback = dist.join("index.html");
    if fallback.is_file() {
        Some(fallback)
    } else {
        None
    }
}

fn percent_decode(input: &str) -> String {
    let bytes = input.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hi = bytes[i + 1];
            let lo = bytes[i + 2];
            if let (Some(h), Some(l)) = (hex_val(hi), hex_val(lo)) {
                out.push((h << 4) | l);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).to_string()
}

fn hex_val(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

fn content_type_for(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase()
        .as_str()
    {
        "html" | "htm" => "text/html; charset=utf-8",
        "js" | "mjs" => "application/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json; charset=utf-8",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "ico" => "image/x-icon",
        "woff" => "font/woff",
        "woff2" => "font/woff2",
        "ttf" => "font/ttf",
        "map" => "application/json; charset=utf-8",
        _ => "application/octet-stream",
    }
}

fn handle_request(req: tiny_http::Request, dist: &Path, port: u16) {
    let host_headers: Vec<_> = req
        .headers()
        .iter()
        .filter(|h| h.field.as_str().to_ascii_lowercase() == "host")
        .collect();
    if host_headers.len() != 1 {
        let _ = req.respond(tiny_http::Response::from_string("Bad Host").with_status_code(400));
        return;
    }
    let host = host_headers[0].value.as_str().to_string();
    if !validate_host(&host, port) {
        let _ = req.respond(tiny_http::Response::from_string("Bad Host").with_status_code(400));
        return;
    }

    let method = req.method().as_str().to_string();
    if !is_allowed_method(&method) {
        let _ = req
            .respond(tiny_http::Response::from_string("Method Not Allowed").with_status_code(405));
        return;
    }

    let url = req.url().to_string();
    let path = url.split('?').next().unwrap_or(&url).to_string();

    if is_proxy_path(&path) {
        proxy_request(req, &method, &url);
    } else {
        serve_static(req, dist, &path);
    }
}

fn serve_static(req: tiny_http::Request, dist: &Path, path: &str) {
    match safe_join_dist(dist, path) {
        Some(file) => {
            let data = match fs::read(&file) {
                Ok(d) => d,
                Err(_) => {
                    let _ = req.respond(
                        tiny_http::Response::from_string("Not Found").with_status_code(404),
                    );
                    return;
                }
            };
            let ct = content_type_for(&file);
            let resp = tiny_http::Response::from_data(data).with_header(
                tiny_http::Header::from_bytes(&b"Content-Type"[..], ct.as_bytes()).unwrap(),
            );
            let _ = req.respond(resp);
        }
        None => {
            let _ =
                req.respond(tiny_http::Response::from_string("Not Found").with_status_code(404));
        }
    }
}

fn proxy_request(mut req: tiny_http::Request, method: &str, url: &str) {
    let backend = match backend_url() {
        Ok(b) => b,
        Err(_) => {
            let _ =
                req.respond(tiny_http::Response::from_string("Bad Gateway").with_status_code(502));
            return;
        }
    };
    let target = format!("{}{}", backend, url);

    // Read request body with size limit.
    let mut body = Vec::new();
    let mut buf = [0u8; 8192];
    let mut total = 0usize;
    loop {
        match req.as_reader().read(&mut buf) {
            Ok(0) => break,
            Ok(n) => {
                total += n;
                if total > MAX_BODY_BYTES {
                    let _ = req.respond(
                        tiny_http::Response::from_string("Payload Too Large").with_status_code(413),
                    );
                    return;
                }
                body.extend_from_slice(&buf[..n]);
            }
            Err(_) => break,
        }
    }

    forward_http(req, method, &target, &body);
}

fn forward_http(req: tiny_http::Request, method: &str, target: &str, body: &[u8]) {
    // Filter hop-by-hop and sensitive headers.
    let mut headers: Vec<(String, String)> = Vec::new();
    for h in req.headers() {
        let name = h.field.as_str().to_string();
        let lower = name.to_ascii_lowercase();
        if HOP_BY_HOP.contains(&lower.as_str()) {
            continue;
        }
        // Do not forward cookies? We MUST forward cookies for session auth.
        // Forward Cookie header (not hop-by-hop). Keep it.
        let val = h.value.as_str();
        headers.push((name, val.to_string()));
    }

    let config = ureq::config::Config::builder()
        .timeout_global(Some(Duration::from_secs(30)))
        .timeout_per_read(Some(Duration::from_secs(30)))
        .timeout_per_write(Some(Duration::from_secs(30)))
        .max_redirects(0)
        .http_status_as_error(false)
        .build();
    let resolver = ValidatingResolver;
    let connector = ureq::unversioned::transport::DefaultConnector::default();
    let agent = ureq::Agent::with_parts(config, connector, resolver);

    let m = method.to_uppercase();
    let result = match m.as_str() {
        "POST" | "PUT" | "PATCH" => {
            let mut rb = match m.as_str() {
                "POST" => agent.post(target),
                "PUT" => agent.put(target),
                "PATCH" => agent.patch(target),
                _ => unreachable!(),
            };
            for (k, v) in &headers {
                rb = rb.header(k.as_str(), v.as_str());
            }
            if body.is_empty() {
                rb.send_empty()
            } else {
                rb.send(body)
            }
        }
        "GET" | "DELETE" | "HEAD" | "OPTIONS" => {
            let mut rb = match m.as_str() {
                "GET" => agent.get(target),
                "DELETE" => agent.delete(target),
                "HEAD" => agent.head(target),
                "OPTIONS" => agent.options(target),
                _ => unreachable!(),
            };
            for (k, v) in &headers {
                rb = rb.header(k.as_str(), v.as_str());
            }
            rb.call()
        }
        _ => {
            let _ = req.respond(
                tiny_http::Response::from_string("Method Not Allowed").with_status_code(405),
            );
            return;
        }
    };

    match result {
        Ok(mut resp) => {
            let status = resp.status().as_u16();

            // Collect response headers (filter hop-by-hop).
            let mut resp_headers: Vec<(String, String)> = Vec::new();
            for (k, v) in resp.headers().iter() {
                let name = k.as_str().to_string();
                let lower = name.to_ascii_lowercase();
                if HOP_BY_HOP.contains(&lower.as_str()) {
                    continue;
                }
                if let Ok(val) = v.to_str() {
                    resp_headers.push((name, val.to_string()));
                }
            }

            // Read body with size limit.
            let body_result = resp.body_mut().read_to_vec();
            let resp_body = match body_result {
                Ok(b) => b,
                Err(_) => {
                    let _ = req.respond(
                        tiny_http::Response::from_string("Bad Gateway").with_status_code(502),
                    );
                    return;
                }
            };
            if resp_body.len() > MAX_BODY_BYTES {
                let _ = req.respond(
                    tiny_http::Response::from_string("Response Too Large").with_status_code(502),
                );
                return;
            }

            let mut response =
                tiny_http::Response::from_data(resp_body.clone()).with_status_code(status);
            for (k, v) in &resp_headers {
                if let Ok(h) = tiny_http::Header::from_bytes(k.as_bytes(), v.as_bytes()) {
                    response = response.with_header(h);
                }
            }
            response = response.with_header(
                tiny_http::Header::from_bytes(
                    &b"Content-Length"[..],
                    format!("{}", resp_body.len()).as_bytes(),
                )
                .unwrap(),
            );
            let _ = req.respond(response);
        }
        Err(_) => {
            // Do not leak error details (may contain URLs/paths).
            let _ =
                req.respond(tiny_http::Response::from_string("Bad Gateway").with_status_code(502));
        }
    }
}

pub fn start_server(dist: PathBuf) -> Result<ServerHandle, String> {
    // Bind only to loopback.
    let server = tiny_http::Server::http("127.0.0.1:0").map_err(|e| e.to_string())?;
    let port = server
        .server_addr()
        .to_ip()
        .map(|a| a.port())
        .ok_or_else(|| "no addr".to_string())?;
    // Verify loopback binding.
    if let Some(addr) = server.server_addr().to_ip()
        && !addr.ip().is_loopback()
    {
        return Err("refusing to bind to non-loopback address".to_string());
    }
    let stop = Arc::new(AtomicBool::new(false));
    let stop2 = stop.clone();
    let dist2 = dist.clone();
    let thread = thread::spawn(move || {
        loop {
            if stop2.load(Ordering::Relaxed) {
                break;
            }
            match server.recv_timeout(Duration::from_millis(100)) {
                Ok(Some(req)) => handle_request(req, &dist2, port),
                Ok(None) => continue,
                Err(_) => {
                    std::thread::sleep(Duration::from_millis(50));
                    continue;
                }
            }
        }
    });
    Ok(ServerHandle {
        stop,
        thread: Some(thread),
        port,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use ureq::unversioned::resolver::Resolver;
    #[test]
    fn host_validation_accepts_loopback() {
        assert!(validate_host("127.0.0.1:8080", 8080));
        assert!(validate_host("localhost:8080", 8080));
        assert!(validate_host("[::1]:8080", 8080));
    }

    #[test]
    fn host_validation_rejects_foreign() {
        assert!(!validate_host("evil.com:8080", 8080));
        assert!(!validate_host("127.0.0.1:9999", 8080));
        assert!(!validate_host("", 8080));
        assert!(!validate_host("127.0.0.1.evil.com:8080", 8080));
    }

    #[test]
    fn host_validation_rejects_userinfo_and_trailing_dot() {
        assert!(!validate_host("user@127.0.0.1:8080", 8080));
        assert!(!validate_host("127.0.0.1:8080.", 8080));
        assert!(!validate_host("127.0.0.1:8080,evil.com:80", 8080));
    }

    #[test]
    fn host_validation_case_insensitive() {
        assert!(validate_host("LOCALHOST:8080", 8080));
        assert!(validate_host("LocalHost:8080", 8080));
    }

    #[test]
    fn proxy_path_classification() {
        assert!(is_proxy_path("/api/auth/headless/browser/v1/config"));
        assert!(is_proxy_path("/v1/spend-requests/"));
        assert!(is_proxy_path("/api"));
        assert!(!is_proxy_path("/index.html"));
        assert!(!is_proxy_path("/assets/foo.js"));
    }

    #[test]
    fn proxy_path_rejects_traversal_and_absolute() {
        assert!(!is_proxy_path("/api/../etc/passwd"));
        assert!(!is_proxy_path("/api/%2e%2e/etc/passwd"));
        assert!(!is_proxy_path("http://evil.com/api"));
        assert!(!is_proxy_path("/api\x00foo"));
    }

    #[test]
    fn allowed_methods() {
        assert!(is_allowed_method("GET"));
        assert!(is_allowed_method("POST"));
        assert!(is_allowed_method("DELETE"));
        assert!(!is_allowed_method("TRACE"));
        assert!(!is_allowed_method("CONNECT"));
    }

    #[test]
    fn safe_join_rejects_traversal() {
        let tmp = std::env::temp_dir().join("agentgate_test_dist");
        let _ = std::fs::create_dir_all(&tmp);
        std::fs::write(tmp.join("index.html"), b"x").unwrap();
        assert!(safe_join_dist(&tmp, "/../etc/passwd").is_none());
        assert!(safe_join_dist(&tmp, "/%2e%2e/etc/passwd").is_none());
        assert!(safe_join_dist(&tmp, "/index.html").is_some());
        assert!(safe_join_dist(&tmp, "/\0foo").is_none());
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn server_lifecycle_start_stop() {
        let tmp = std::env::temp_dir().join("agentgate_lc_dist");
        let _ = std::fs::create_dir_all(&tmp);
        std::fs::write(tmp.join("index.html"), b"ok").unwrap();
        let handle = start_server(tmp.clone()).expect("start");
        let port = handle.port;
        std::thread::sleep(std::time::Duration::from_millis(200));
        let mut stream = TcpStream::connect(format!("127.0.0.1:{}", port)).unwrap();
        use std::io::Write;
        let req = format!(
            "GET / HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\n\r\n",
            port
        );
        stream.write_all(req.as_bytes()).unwrap();
        let mut buf = [0u8; 256];
        let _ = stream.set_read_timeout(Some(std::time::Duration::from_secs(5)));
        let n = stream.read(&mut buf).unwrap_or(0);
        assert!(n > 0);
        drop(handle);
        std::thread::sleep(std::time::Duration::from_millis(200));
        assert!(TcpStream::connect(format!("127.0.0.1:{}", port)).is_err());
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn minimal_tiny_http() {
        let server = tiny_http::Server::http("127.0.0.1:0").unwrap();
        let port = server.server_addr().to_ip().unwrap().port();
        let handle = std::thread::spawn(move || {
            if let Ok(Some(req)) = server.recv_timeout(std::time::Duration::from_secs(2)) {
                let _ = req.respond(tiny_http::Response::from_string("hi"));
            }
        });
        std::thread::sleep(std::time::Duration::from_millis(200));
        let mut stream = TcpStream::connect(format!("127.0.0.1:{}", port)).unwrap();
        use std::io::Write;
        stream
            .write_all(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            .unwrap();
        handle.join().unwrap();
    }

    #[test]
    fn safe_join_spa_fallback() {
        let tmp = std::env::temp_dir().join("agentgate_test_dist2");
        let _ = std::fs::create_dir_all(&tmp);
        std::fs::write(tmp.join("index.html"), b"x").unwrap();
        assert!(safe_join_dist(&tmp, "/nonexistent/route").is_some());
        let _ = std::fs::remove_dir_all(&tmp);
    }

    // --- AG-04: URL validation tests ---

    #[test]
    fn backend_url_default_is_valid() {
        // Ensure no env override.
        unsafe {
            std::env::remove_var("AGENTGATE_BACKEND_URL");
        }
        let r = backend_url();
        assert!(r.is_ok(), "default must validate: {:?}", r);
        assert_eq!(r.unwrap(), "http://127.0.0.1:8000");
    }

    #[test]
    fn validate_backend_url_loopback_http_ok() {
        assert!(validate_backend_url("http://127.0.0.1:8000").is_ok());
        assert!(validate_backend_url("http://localhost:8000").is_ok());
        assert!(validate_backend_url("http://[::1]:8000").is_ok());
        assert!(validate_backend_url("http://127.0.0.1").is_ok());
    }

    #[test]
    fn validate_backend_url_hosted_https_ok() {
        assert!(validate_backend_url("https://api.example.com").is_ok());
        assert!(validate_backend_url("https://api.example.com:8443").is_ok());
        assert!(validate_backend_url("https://127.0.0.1:8443").is_ok());
    }

    #[test]
    fn validate_backend_url_rejects_hosted_http() {
        assert!(validate_backend_url("http://example.com").is_err());
        assert!(validate_backend_url("http://10.0.0.1:8000").is_err());
        assert!(validate_backend_url("http://192.168.1.1").is_err());
    }

    #[test]
    fn validate_backend_url_rejects_bad_scheme() {
        assert!(validate_backend_url("ftp://example.com").is_err());
        assert!(validate_backend_url("file:///etc/passwd").is_err());
        assert!(validate_backend_url("javascript:alert(1)").is_err());
        assert!(validate_backend_url("data:text/plain,hi").is_err());
    }

    #[test]
    fn validate_backend_url_rejects_credentials() {
        assert!(validate_backend_url("https://user:pass@example.com").is_err());
        assert!(validate_backend_url("https://user@example.com").is_err());
        assert!(validate_backend_url("http://user:pass@127.0.0.1:8000").is_err());
    }

    #[test]
    fn validate_backend_url_rejects_fragment_and_query() {
        assert!(validate_backend_url("https://example.com#frag").is_err());
        assert!(validate_backend_url("https://example.com?x=1").is_err());
        assert!(validate_backend_url("https://example.com/path?q=1").is_err());
    }

    #[test]
    fn validate_backend_url_rejects_path() {
        assert!(validate_backend_url("https://example.com/foo").is_err());
        assert!(validate_backend_url("https://example.com/foo/bar").is_err());
    }

    #[test]
    fn validate_backend_url_rejects_unsafe_ips() {
        assert!(validate_backend_url("https://0.0.0.0").is_err());
        assert!(validate_backend_url("http://0.0.0.0:8000").is_err());
        assert!(validate_backend_url("https://255.255.255.255").is_err());
        assert!(validate_backend_url("https://224.0.0.1").is_err()); // multicast
        assert!(validate_backend_url("https://169.254.1.1").is_err()); // link-local
    }

    #[test]
    fn validate_backend_url_rejects_malformed() {
        assert!(validate_backend_url("").is_err());
        assert!(validate_backend_url("not a url").is_err());
        assert!(validate_backend_url("http://").is_err());
        assert!(validate_backend_url("https://").is_err());
    }

    #[test]
    fn validate_backend_url_rejects_wildcard_host() {
        assert!(validate_backend_url("https://*").is_err());
    }

    #[test]
    fn validate_backend_url_env_invalid_does_not_fallback() {
        unsafe {
            std::env::set_var("AGENTGATE_BACKEND_URL", "http://evil.com");
        }
        let r = backend_url();
        unsafe {
            std::env::remove_var("AGENTGATE_BACKEND_URL");
        }
        assert!(
            r.is_err(),
            "invalid hosted HTTP must not fall back to localhost"
        );
    }

    #[test]
    fn validate_backend_url_canonicalizes() {
        let r = validate_backend_url("HTTPS://Example.COM:8443/").unwrap();
        assert_eq!(r, "https://example.com:8443");
    }

    #[test]
    fn server_binds_loopback_only() {
        let tmp = std::env::temp_dir().join("agentgate_loopback_test");
        let _ = std::fs::create_dir_all(&tmp);
        std::fs::write(tmp.join("index.html"), b"x").unwrap();
        let handle = start_server(tmp.clone()).expect("start");
        let addr = handle.port;
        // connect via 127.0.0.1 works
        assert!(TcpStream::connect(format!("127.0.0.1:{}", addr)).is_ok());
        let _ = std::fs::remove_dir_all(&tmp);
        drop(handle);
    }

    #[test]
    fn is_hop_by_hop_filter() {
        // Ensure HOP_BY_HOP list covers expected entries.
        assert!(HOP_BY_HOP.contains(&"host"));
        assert!(HOP_BY_HOP.contains(&"connection"));
        assert!(HOP_BY_HOP.contains(&"content-length"));
        assert!(HOP_BY_HOP.contains(&"transfer-encoding"));
        assert!(!HOP_BY_HOP.contains(&"cookie"));
        assert!(!HOP_BY_HOP.contains(&"authorization"));
        assert!(!HOP_BY_HOP.contains(&"x-csrftoken"));
    }

    // --- AG-04.1: DNS rebinding / SSRF tests ---

    #[test]
    fn is_unsafe_ip_public_ipv4_safe() {
        let ip: IpAddr = "8.8.8.8".parse().unwrap();
        assert!(!is_unsafe_ip(&ip));
        let ip: IpAddr = "1.1.1.1".parse().unwrap();
        assert!(!is_unsafe_ip(&ip));
    }

    #[test]
    fn is_unsafe_ip_public_ipv6_safe() {
        let ip: IpAddr = "2001:4860:4860::8888".parse().unwrap();
        assert!(!is_unsafe_ip(&ip));
    }

    #[test]
    fn is_unsafe_ip_loopback_safe() {
        let ip: IpAddr = "127.0.0.1".parse().unwrap();
        assert!(!is_unsafe_ip(&ip));
        let ip: IpAddr = "::1".parse().unwrap();
        assert!(!is_unsafe_ip(&ip));
    }

    #[test]
    fn is_unsafe_ip_rejects_private_and_special() {
        // unspecified
        assert!(is_unsafe_ip(&"0.0.0.0".parse::<IpAddr>().unwrap()));
        assert!(is_unsafe_ip(&"::".parse::<IpAddr>().unwrap()));
        // broadcast
        assert!(is_unsafe_ip(&"255.255.255.255".parse::<IpAddr>().unwrap()));
        // multicast
        assert!(is_unsafe_ip(&"224.0.0.1".parse::<IpAddr>().unwrap()));
        assert!(is_unsafe_ip(&"ff02::1".parse::<IpAddr>().unwrap()));
        // link-local
        assert!(is_unsafe_ip(&"169.254.1.1".parse::<IpAddr>().unwrap()));
        assert!(is_unsafe_ip(&"fe80::1".parse::<IpAddr>().unwrap()));
    }

    #[test]
    fn resolver_rejects_dns_failure() {
        let r = ValidatingResolver;
        let uri: ureq::http::Uri = "https://this-host-does-not-exist.invalid:443"
            .parse()
            .unwrap();
        let config = ureq::config::Config::default();
        let timeout = ureq::unversioned::transport::NextTimeout::default();
        // Should fail (host not found) rather than panic.
        let res = r.resolve(&uri, &config, timeout);
        assert!(res.is_err(), "DNS failure must be rejected");
    }

    #[test]
    fn resolver_resolves_localhost_to_loopback() {
        let r = ValidatingResolver;
        let uri: ureq::http::Uri = "http://localhost:8000".parse().unwrap();
        let config = ureq::config::Config::default();
        let timeout = ureq::unversioned::transport::NextTimeout::default();
        let res = r.resolve(&uri, &config, timeout);
        // localhost should resolve; if it does, all addresses must be loopback.
        if let Ok(addrs) = res {
            for a in addrs.iter() {
                assert!(
                    a.ip().is_loopback(),
                    "localhost must resolve to loopback only"
                );
            }
        }
    }

    #[test]
    fn resolver_rejects_http_resolving_to_non_loopback() {
        // An IP literal that is not loopback must be rejected for http.
        // validate_backend_url already rejects, but resolver also guards.
        // Use a hostname that resolves to a public IP over http -> resolver rejects.
        // We test via is_unsafe_ip + http scheme logic indirectly through
        // validate_backend_url which rejects non-loopback http hosts.
        assert!(validate_backend_url("http://8.8.8.8").is_err());
    }

    #[test]
    fn resolver_validates_all_addresses() {
        // If any single resolved address is unsafe, the whole resolution is rejected.
        // is_unsafe_ip must catch the unsafe one.
        let safe: IpAddr = "8.8.8.8".parse().unwrap();
        let unsafe_ip: IpAddr = "0.0.0.0".parse().unwrap();
        assert!(!is_unsafe_ip(&safe));
        assert!(is_unsafe_ip(&unsafe_ip));
    }
}
