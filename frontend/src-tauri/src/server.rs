#![allow(dead_code)]

use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread::{self, JoinHandle};
use std::time::Duration;

const BACKEND: &str = "http://127.0.0.1:8000";
const MAX_BODY_BYTES: usize = 10 * 1024 * 1024;
const PROXY_PATHS: [&str; 2] = ["/api", "/v1"];
const ALLOWED_METHODS: [&str; 7] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];

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
    let target = format!("{}{}", BACKEND, url);
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
    let parsed = target.trim_start_matches("http://");
    let (hostport, path) = match parsed.find('/') {
        Some(i) => (&parsed[..i], &parsed[i..]),
        None => (parsed, "/"),
    };
    let hostport = if hostport.is_empty() {
        "127.0.0.1:8000"
    } else {
        hostport
    };

    let mut stream = match TcpStream::connect(hostport) {
        Ok(s) => s,
        Err(_) => {
            let _ =
                req.respond(tiny_http::Response::from_string("Bad Gateway").with_status_code(502));
            return;
        }
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(30)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(30)));

    let mut request = format!("{} {} HTTP/1.1\r\n", method, path);
    request.push_str(&format!("Host: {}\r\n", hostport));
    for h in req.headers() {
        let name = h.field.as_str();
        let lower = name.to_ascii_lowercase();
        if lower == "host" || lower == "connection" || lower == "content-length" {
            continue;
        }
        request.push_str(&format!("{}: {}\r\n", name, h.value));
    }
    request.push_str(&format!("Content-Length: {}\r\n", body.len()));
    request.push_str("Connection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() || stream.write_all(body).is_err() {
        let _ = req.respond(tiny_http::Response::from_string("Bad Gateway").with_status_code(502));
        return;
    }

    let mut resp_bytes = Vec::new();
    let mut buf = [0u8; 8192];
    loop {
        match stream.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => {
                if resp_bytes.len() + n > MAX_BODY_BYTES {
                    let _ = req.respond(
                        tiny_http::Response::from_string("Response Too Large")
                            .with_status_code(502),
                    );
                    return;
                }
                resp_bytes.extend_from_slice(&buf[..n]);
            }
            Err(_) => break,
        }
    }

    let sep = b"\r\n\r\n";
    let status_code: u16 = String::from_utf8_lossy(&resp_bytes)
        .lines()
        .next()
        .unwrap_or("")
        .split_whitespace()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(502);

    let mut headers: Vec<(String, String)> = Vec::new();
    let mut body_start = resp_bytes.len();
    if let Some(pos) = resp_bytes.windows(4).position(|w| w == sep) {
        body_start = pos + 4;
        let header_text = String::from_utf8_lossy(&resp_bytes[..pos]);
        for line in header_text.lines().skip(1) {
            if let Some((k, v)) = line.split_once(':') {
                headers.push((k.trim().to_string(), v.trim().to_string()));
            }
        }
    }
    let resp_body = &resp_bytes[body_start..];

    let mut response =
        tiny_http::Response::from_data(resp_body.to_vec()).with_status_code(status_code);
    for (k, v) in headers {
        let lower = k.to_ascii_lowercase();
        if lower == "transfer-encoding"
            || lower == "connection"
            || lower == "content-encoding"
            || lower == "content-length"
        {
            continue;
        }
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

pub fn start_server(dist: PathBuf) -> Result<ServerHandle, String> {
    let server = tiny_http::Server::http("127.0.0.1:0").map_err(|e| e.to_string())?;
    let port = server
        .server_addr()
        .to_ip()
        .map(|a| a.port())
        .ok_or_else(|| "no addr".to_string())?;
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
    use std::path::PathBuf;

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
        // server responds
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
        // drop handle -> stop
        drop(handle);
        // port should be closed (connection refused)
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
            } else {
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
}
