import SwiftUI
import AppKit

@main
struct SafariMagicHubApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .onOpenURL { url in
                    handleIncomingFile(url: url)
                }
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified)
        .commands {
            SidebarCommands()
            CommandGroup(replacing: .newItem) {
                Button("Install Extension Package...") {
                    let panel = NSOpenPanel()
                    panel.allowsMultipleSelection = false
                    panel.canChooseDirectories = false
                    panel.prompt = "Install into Safari"
                    if panel.runModal() == .OK, let u = panel.url {
                        _ = try? PackageManager.shared.installPackage(from: u, relaunchSafari: true)
                    }
                }
                .keyboardShortcut("o", modifiers: .command)
            }
        }
    }

    private func handleIncomingFile(url: URL) {
        guard url.pathExtension.lowercased() == "magicext" || url.pathExtension.lowercased() == "zip" else { return }
        do {
            _ = try PackageManager.shared.installPackage(from: url, relaunchSafari: true)
        } catch {
            NSSound.beep()
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func application(_ sender: NSApplication, openFile filename: String) -> Bool {
        let url = URL(fileURLWithPath: filename)
        if url.pathExtension.lowercased() == "magicext" || url.pathExtension.lowercased() == "zip" {
            do {
                _ = try PackageManager.shared.installPackage(from: url, relaunchSafari: true)
                return true
            } catch {
                return false
            }
        }
        return false
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
}
