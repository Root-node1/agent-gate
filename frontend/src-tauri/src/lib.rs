pub mod server;

#[cfg(not(debug_assertions))]
use tauri::Manager;
use tauri::{WebviewUrl, WebviewWindowBuilder};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            #[cfg(debug_assertions)]
            let url = "http://localhost:5173".to_string();
            #[cfg(not(debug_assertions))]
            let url = {
                let mut dist = std::path::PathBuf::from("dist");
                if !dist.exists() {
                    dist = std::path::PathBuf::from("../dist");
                }
                if !dist.exists() {
                    if let Ok(rd) = app.path().resource_dir() {
                        let c = rd.join("frontend").join("dist");
                        if c.exists() {
                            dist = c;
                        } else {
                            let c2 = rd.join("dist");
                            if c2.exists() {
                                dist = c2;
                            }
                        }
                    }
                }
                if !dist.exists() {
                    dist = std::path::PathBuf::from("frontend/dist");
                }
                match server::start_server(dist) {
                    Ok(handle) => {
                        let port = handle.port;
                        app.manage(handle);
                        format!("http://127.0.0.1:{}", port)
                    }
                    Err(e) => {
                        eprintln!("failed to start desktop server: {}", e);
                        "http://127.0.0.1:8000".to_string()
                    }
                }
            };

            let _ =
                WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url.parse().unwrap()))
                    .title("AgentGate Desktop")
                    .inner_size(800.0, 600.0)
                    .min_inner_size(800.0, 600.0)
                    .center()
                    .build();
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}
