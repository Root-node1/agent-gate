use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::thread;
use std::time::Duration;

fn http(port: u16, req: &str) -> String {
    let mut stream = TcpStream::connect(format!("127.0.0.1:{port}")).unwrap();
    stream.write_all(req.as_bytes()).unwrap();
    let mut buf = Vec::new();
    stream.read_to_end(&mut buf).unwrap();
    String::from_utf8_lossy(&buf).into_owned()
}

fn main() {
    let dist = PathBuf::from(std::env::var("PROBE_DIST").expect("PROBE_DIST"));
    let handle = app_lib::server::start_server(dist).expect("start");
    let port = handle.port;
    thread::sleep(Duration::from_millis(150));

    let backend = std::env::var("PROBE_BACKEND").unwrap_or_else(|_| "http://127.0.0.1:18000".into());
    let body = format!("{{\"url\":\"{backend}\"}}");
    let put = http(port, &format!(
        "PUT /__agentgate/backend HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    ));
    assert!(put.contains("200 OK"), "{put}");

    let probe = http(port, &format!(
        "POST /__agentgate/backend/probe HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    ));
    assert!(probe.contains("200 OK"), "{probe}");
    assert!(probe.contains("\"ok\":true"), "{probe}");
    println!("DESKTOP_BACKEND_PROBE_OK");

    let health = http(port, &format!(
        "GET /api/health/ HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    ));
    assert!(health.contains("200 OK"), "{health}");
    println!("DESKTOP_PROXY_HEALTH_OK");

    let body = r#"{"url":"http://127.0.0.1:9"}"#;
    let put2 = http(port, &format!(
        "PUT /__agentgate/backend HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    ));
    assert!(put2.contains("200 OK"), "{put2}");
    let probe_fail = http(port, &format!(
        "POST /__agentgate/backend/probe HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    ));
    assert!(probe_fail.contains("\"ok\":false"), "{probe_fail}");
    println!("DESKTOP_BACKEND_FAILURE_OK");
    drop(handle);
}
