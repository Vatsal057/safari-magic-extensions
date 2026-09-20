import SwiftUI
import AppKit
import UniformTypeIdentifiers

public struct ContentView: View {
    @State private var selectedTab: TabOption = .installed
    @State private var installed: [InstalledExtension] = []
    @State private var installedSearch: String = ""
    @State private var communitySearch: String = ""
    @State private var statusMessage: String = "Ready"
    @State private var isPermissionDenied: Bool = false
    @State private var isDropTargeted: Bool = false
    @State private var selectedInstalled: InstalledExtension? = nil
    @State private var selectedCommunity: CommunityExtension? = nil
    @State private var installingId: String? = nil

    @StateObject private var registry = CommunityRegistryClient.shared

    public init() {}

    enum TabOption: String, CaseIterable, Identifiable {
        case installed = "My Extensions"
        case community = "Community Hub"
        var id: String { self.rawValue }
        var icon: String {
            switch self {
            case .installed: return "puzzlepiece.extension.fill"
            case .community: return "globe.americas.fill"
            }
        }
    }

    public var body: some View {
        NavigationSplitView {
            List(TabOption.allCases, selection: $selectedTab) { tab in
                Label(tab.rawValue, systemImage: tab.icon)
                    .tag(tab)
                    .font(.system(size: 13, weight: .medium))
            }
            .listStyle(.sidebar)
            .navigationSplitViewColumnWidth(min: 170, ideal: 190, max: 230)
        } detail: {
            VStack(spacing: 0) {
                switch selectedTab {
                case .installed:
                    installedView
                case .community:
                    communityView
                }

                Divider()

                // Bottom Status Bar
                HStack {
                    Text(statusMessage)
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Spacer()
                    Text("Safari Magic Hub")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary.opacity(0.7))
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(.bar)
            }
        }
        .frame(minWidth: 780, minHeight: 520)
        .onAppear {
            refreshInstalled()
            Task { await registry.fetchCatalog() }
        }
        .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted) { providers in
            handleDrop(providers: providers)
        }
        .overlay {
            if isDropTargeted {
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.accentColor, lineWidth: 3)
                    .background(Color.accentColor.opacity(0.08))
                    .overlay(
                        VStack(spacing: 8) {
                            Image(systemName: "arrow.down.doc.fill")
                                .font(.system(size: 44))
                                .foregroundColor(.accentColor)
                            Text("Drop .magicext to Install in Safari")
                                .font(.title3.bold())
                        }
                    )
                    .padding(8)
            }
        }
    }

    // =====================================================================
    //  TAB 1: Installed View
    // =====================================================================
    private var installedView: some View {
        VStack(spacing: 0) {
            // Header Toolbar
            HStack(spacing: 12) {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Search installed extensions...", text: $installedSearch)
                        .textFieldStyle(.plain)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)

                Spacer()

                Button {
                    refreshInstalled()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Refresh Extensions")

                Button {
                    chooseAndInstallPackage()
                } label: {
                    Label("Install .magicext", systemImage: "plus.app.fill")
                }
                .buttonStyle(.borderedProminent)
            }
            .padding(14)
            .background(.bar)

            Divider()

            let filtered = installed.filter {
                installedSearch.isEmpty ||
                $0.name.localizedCaseInsensitiveContains(installedSearch) ||
                $0.prompt.localizedCaseInsensitiveContains(installedSearch)
            }

            if isPermissionDenied && installed.isEmpty {
                VStack(spacing: 16) {
                    Spacer()
                    Image(systemName: "lock.shield.fill")
                        .font(.system(size: 52))
                        .foregroundColor(.orange)

                    Text("Full Disk Access Required")
                        .font(.title2.bold())

                    Text("macOS restricts apps from accessing Safari's internal data container (`~/Library/Containers/com.apple.Safari`).\n\nTo view and manage your installed extensions, grant Safari Magic Hub Full Disk Access in macOS System Settings.")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 500)

                    HStack(spacing: 12) {
                        Button {
                            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles") {
                                NSWorkspace.shared.open(url)
                            }
                        } label: {
                            Label("Open Full Disk Access Settings", systemImage: "gearshape.fill")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)

                        Button {
                            refreshInstalled()
                        } label: {
                            Label("Check Again", systemImage: "arrow.clockwise")
                                .font(.system(size: 12))
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.large)
                    }
                    .padding(.top, 4)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("💡 Or launch directly via Terminal (No settings required):")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(.secondary)
                        Text("./SafariMagicHub.app/Contents/MacOS/SafariMagicHub")
                            .font(.system(size: 11, design: .monospaced))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color(NSColor.controlBackgroundColor))
                            .cornerRadius(6)
                    }
                    .padding(12)
                    .background(Color(NSColor.windowBackgroundColor).opacity(0.5))
                    .cornerRadius(8)

                    Spacer()
                }
                .padding(24)
            } else if filtered.isEmpty {
                VStack(spacing: 12) {
                    Spacer()
                    Image(systemName: "puzzlepiece.extension")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary.opacity(0.5))
                    Text("No Extensions Found")
                        .font(.headline)
                        .foregroundColor(.secondary)
                    Text("Drop a .magicext file or install from the Community Hub.")
                        .font(.subheadline)
                        .foregroundColor(.secondary.opacity(0.8))
                    Spacer()
                }
            } else {
                List(filtered, id: \.id, selection: $selectedInstalled) { ext in
                    InstalledRow(ext: ext) {
                        packForSharing(ext: ext)
                    }
                    .padding(.vertical, 4)
                }
                .listStyle(.inset(alternatesRowBackgrounds: true))
            }
        }
    }

    // =====================================================================
    //  TAB 2: Community View
    // =====================================================================
    private var communityView: some View {
        VStack(spacing: 0) {
            // Header Toolbar
            HStack(spacing: 12) {
                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(.secondary)
                    TextField("Search community extensions or prompts...", text: $communitySearch)
                        .textFieldStyle(.plain)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(Color(NSColor.controlBackgroundColor))
                .cornerRadius(8)

                Spacer()

                if registry.isLoading {
                    ProgressView().scaleEffect(0.8)
                }

                Button {
                    Task { await registry.fetchCatalog() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("Refresh Catalog")
            }
            .padding(14)
            .background(.bar)

            Divider()

            let filtered = registry.extensions.filter {
                communitySearch.isEmpty ||
                $0.name.localizedCaseInsensitiveContains(communitySearch) ||
                ($0.prompt ?? "").localizedCaseInsensitiveContains(communitySearch) ||
                ($0.description ?? "").localizedCaseInsensitiveContains(communitySearch)
            }

            if filtered.isEmpty {
                VStack(spacing: 12) {
                    Spacer()
                    Image(systemName: "sparkles")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary.opacity(0.5))
                    Text("No Extensions Found")
                        .font(.headline)
                        .foregroundColor(.secondary)
                    Spacer()
                }
            } else {
                List(filtered, id: \.id) { item in
                    CommunityRow(item: item, isInstalling: installingId == item.id) {
                        installCommunityItem(item: item)
                    }
                    .padding(.vertical, 6)
                }
                .listStyle(.inset(alternatesRowBackgrounds: true))
            }
        }
    }

    // =====================================================================
    //  Actions
    // =====================================================================
    private func refreshInstalled() {
        let res = ExtensionDatabase.shared.fetchInstalledExtensionsWithStatus()
        installed = res.extensions
        isPermissionDenied = res.isPermissionDenied
        if let err = res.error {
            statusMessage = "DB Notice: \(err)"
        } else {
            statusMessage = "Loaded \(installed.count) active Safari extensions."
        }
    }

    private func chooseAndInstallPackage() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "magicext") ?? .archive, .zip]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.prompt = "Install into Safari"

        if panel.runModal() == .OK, let url = panel.url {
            do {
                let id = try PackageManager.shared.installPackage(from: url, relaunchSafari: true)
                refreshInstalled()
                statusMessage = "Installed: \(url.deletingPathExtension().lastPathComponent) [\(id)]"
            } catch {
                NSSound.beep()
                statusMessage = "Install failed: \(error.localizedDescription)"
            }
        }
    }

    private func packForSharing(ext: InstalledExtension) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        panel.prompt = "Save .magicext Package"

        if panel.runModal() == .OK, let dest = panel.url {
            do {
                let out = try PackageManager.shared.pack(extension: ext, destinationDir: dest)
                statusMessage = "Packaged to \(out.lastPathComponent)"
                NSWorkspace.shared.activateFileViewerSelecting([out])
            } catch {
                NSSound.beep()
                statusMessage = "Packaging error: \(error.localizedDescription)"
            }
        }
    }

    private func installCommunityItem(item: CommunityExtension) {
        installingId = item.id
        statusMessage = "Downloading \(item.name)..."
        Task {
            do {
                let id = try await registry.downloadAndInstall(extension: item)
                await MainActor.run {
                    installingId = nil
                    refreshInstalled()
                    statusMessage = "Installed \(item.name) into Safari! [\(id)]"
                }
            } catch {
                await MainActor.run {
                    installingId = nil
                    NSSound.beep()
                    statusMessage = "Failed: \(error.localizedDescription)"
                }
            }
        }
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                if let data = item as? Data,
                   let url = URL(dataRepresentation: data, relativeTo: nil) {
                    DispatchQueue.main.async {
                        do {
                            let id = try PackageManager.shared.installPackage(from: url, relaunchSafari: true)
                            refreshInstalled()
                            statusMessage = "Installed dropped package: \(url.lastPathComponent) [\(id)]"
                        } catch {
                            NSSound.beep()
                            statusMessage = "Drop install failed: \(error.localizedDescription)"
                        }
                    }
                }
            }
        }
        return true
    }
}

// =========================================================================
//  Subviews: InstalledRow & CommunityRow
// =========================================================================

struct InstalledRow: View {
    let ext: InstalledExtension
    let onPack: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(ext.color.opacity(0.18))
                        .frame(width: 38, height: 38)
                    Image(systemName: ext.selectedSymbol)
                        .font(.system(size: 18))
                        .foregroundColor(ext.color)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(ext.name)
                        .font(.system(size: 14, weight: .bold))
                    Text(ext.directoryName)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.secondary)
                }

                Spacer()

                Button {
                    onPack()
                } label: {
                    Label("Pack .magicext", systemImage: "square.and.arrow.up")
                        .font(.system(size: 11))
                }
                .buttonStyle(.bordered)
            }

            if !ext.prompt.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("AI PROMPT")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.secondary)
                        Spacer()
                        Button {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(ext.prompt, forType: .string)
                        } label: {
                            Label("Copy Prompt", systemImage: "doc.on.doc")
                                .font(.system(size: 10))
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(.accentColor)
                    }

                    Text("\"\(ext.prompt)\"")
                        .font(.system(size: 12, design: .serif))
                        .italic()
                        .foregroundColor(.primary.opacity(0.85))
                        .lineLimit(2)
                }
                .padding(8)
                .background(Color(NSColor.controlBackgroundColor).opacity(0.6))
                .cornerRadius(6)
            }
        }
        .padding(8)
    }
}

struct CommunityRow: View {
    let item: CommunityExtension
    let isInstalling: Bool
    let onInstall: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(item.safeColor.opacity(0.18))
                        .frame(width: 38, height: 38)
                    Image(systemName: item.safeSymbol)
                        .font(.system(size: 18))
                        .foregroundColor(item.safeColor)
                }

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(item.name)
                            .font(.system(size: 14, weight: .bold))
                        if let author = item.author {
                            Text("by @\(author)")
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                        }
                    }
                    if let desc = item.description {
                        Text(desc)
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                if isInstalling {
                    ProgressView().scaleEffect(0.7)
                } else {
                    Button {
                        onInstall()
                    } label: {
                        Label("Install in Safari", systemImage: "arrow.down.circle.fill")
                            .font(.system(size: 11, weight: .semibold))
                    }
                    .buttonStyle(.borderedProminent)
                }
            }

            if let prompt = item.prompt, !prompt.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("AI PROMPT")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.secondary)
                        Spacer()
                        Button {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(prompt, forType: .string)
                        } label: {
                            Label("Copy", systemImage: "doc.on.doc")
                                .font(.system(size: 10))
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(.accentColor)
                    }

                    Text("\"\(prompt)\"")
                        .font(.system(size: 12, design: .serif))
                        .italic()
                        .foregroundColor(.primary.opacity(0.85))
                        .lineLimit(3)
                }
                .padding(8)
                .background(Color(NSColor.controlBackgroundColor).opacity(0.6))
                .cornerRadius(6)
            }
        }
        .padding(8)
    }
}
