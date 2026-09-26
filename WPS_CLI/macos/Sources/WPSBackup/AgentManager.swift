import Foundation
import ServiceManagement
#if canImport(WPSBackupCore)
import WPSBackupCore
#endif

/// 定时任务与登录项管理 —— 经典 LaunchAgent（~/Library/LaunchAgents）
///
/// 不使用 SMAppService：App 为 ad-hoc 签名时，launchd 会为 SMAppService agent 固定 cdhash 约束（LWCR），
/// 重新构建后约束变为空、标记 “needs LWCR update” 且不会自愈，agent 以 OS_REASON_CODESIGNING 被拒绝启动。
/// 经典 plist 没有 LWCR，已在本机生产验证（2026-09-26）。
enum AgentManager {
    static var uid: String { String(getuid()) }
    static var launchAgentsDir: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents")
    }
    static func plistURL(_ label: String) -> URL { launchAgentsDir.appendingPathComponent("\(label).plist") }

    static var appPath: String { Bundle.main.bundlePath }
    static var runnerPath: String { appPath + "/Contents/MacOS/wps-backup-runner" }

    // MARK: 状态（GUI 与 --diagnose 共用）

    static func printJob(_ label: String) -> String? {
        let r = Shell.run("/bin/launchctl", ["print", "gui/\(uid)/\(label)"])
        return r.status == 0 ? r.stdout : nil
    }

    static func disabled(_ label: String) -> Bool {
        isDisabled(label: label, printDisabledOutput:
                    Shell.run("/bin/launchctl", ["print-disabled", "gui/\(uid)"]).stdout)
    }

    static var state: AgentState {
        guard FileManager.default.fileExists(atPath: plistURL(AppConstants.schedulerLabel).path) else {
            return .notRegistered
        }
        return parseAgentState(printOutput: printJob(AppConstants.schedulerLabel),
                               disabled: disabled(AppConstants.schedulerLabel))
    }

    /// launchd 记录的上次退出原因/退出码（排障用）
    static var lastExit: String {
        guard let out = printJob(AppConstants.schedulerLabel) else { return "-" }
        return out.split(separator: "\n")
            .filter { $0.contains("last exit") }
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .joined(separator: "; ")
    }

    // MARK: 安装

    /// 幂等：写入 plist（内容变化时才写），未加载或内容变化时 bootout + bootstrap。
    /// force = 用户显式点击“启用”：同时解除“登录项”中的禁用。
    @discardableResult
    static func installScheduler(stateDir: String, force: Bool = false) -> Bool {
        cleanupSMAppService()
        migrateLegacyAgent(stateDir: stateDir)
        guard let data = try? LaunchAgentPlist.scheduler(runnerPath: runnerPath) else { return false }
        if force {
            Shell.run("/bin/launchctl", ["enable", "gui/\(uid)/\(AppConstants.schedulerLabel)"])
        }
        return install(label: AppConstants.schedulerLabel, data: data, force: force)
    }

    private static func install(label: String, data: Data, force: Bool) -> Bool {
        let url = plistURL(label)
        let changed = (try? Data(contentsOf: url)) != data
        if changed {
            try? FileManager.default.createDirectory(at: launchAgentsDir, withIntermediateDirectories: true)
            do { try data.write(to: url, options: .atomic) } catch {
                NSLog("write \(url.path) failed: \(error)")
                return false
            }
        }
        let loaded = printJob(label) != nil
        if changed || !loaded || force {
            Shell.run("/bin/launchctl", ["bootout", "gui/\(uid)/\(label)"])
            let r = Shell.run("/bin/launchctl", ["bootstrap", "gui/\(uid)", url.path])
            if r.status != 0 { NSLog("bootstrap \(label) failed: \(r.stderr)") }
        }
        return printJob(label) != nil
    }

    static func uninstall(label: String) {
        Shell.run("/bin/launchctl", ["bootout", "gui/\(uid)/\(label)"])
        try? FileManager.default.removeItem(at: plistURL(label))
    }

    /// 立即触发（与定时运行完全相同的环境和锁）
    @discardableResult
    static func kickstart() -> Bool {
        Shell.run("/bin/launchctl", ["kickstart", "gui/\(uid)/\(AppConstants.schedulerLabel)"]).status == 0
    }

    // MARK: 登录时打开 App

    static var launchAtLogin: Bool {
        get { FileManager.default.fileExists(atPath: plistURL(AppConstants.loginLabel).path) }
        set {
            if newValue {
                // 登录项只写入 plist，不立即 bootstrap（RunAtLoad 会立刻再打开一个实例）；下次登录生效
                if let data = try? LaunchAgentPlist.loginItem(appPath: appPath) {
                    try? FileManager.default.createDirectory(at: launchAgentsDir, withIntermediateDirectories: true)
                    try? data.write(to: plistURL(AppConstants.loginLabel), options: .atomic)
                }
            } else {
                uninstall(label: AppConstants.loginLabel)
            }
        }
    }

    /// App 被移动后更新登录项中的路径
    static func refreshLoginItemPath() {
        guard launchAtLogin, let data = try? LaunchAgentPlist.loginItem(appPath: appPath),
              (try? Data(contentsOf: plistURL(AppConstants.loginLabel))) != data else { return }
        try? data.write(to: plistURL(AppConstants.loginLabel), options: .atomic)
    }

    // MARK: 迁移与清理

    static var legacyPlist: URL { plistURL(AppConstants.legacyLabel) }

    /// 旧版 com.wps.backup（直接运行 wps_backup.py run）→ 停用并移入状态目录，避免两个计划同时触发
    static func migrateLegacyAgent(stateDir: String) {
        guard FileManager.default.fileExists(atPath: legacyPlist.path) else { return }
        Shell.run("/bin/launchctl", ["bootout", "gui/\(uid)/\(AppConstants.legacyLabel)"])
        let dest = URL(fileURLWithPath: stateDir).appendingPathComponent("legacy_\(AppConstants.legacyLabel).plist")
        try? FileManager.default.removeItem(at: dest)
        try? FileManager.default.moveItem(at: legacyPlist, to: dest)
    }

    /// 移除早期版本注册的 SMAppService agent / 登录项（否则失效的 agent 每小时 spawn failed）
    static func cleanupSMAppService() {
        let agent = SMAppService.agent(plistName: AppConstants.smAgentPlistName)
        if agent.status != .notRegistered && agent.status != .notFound {
            try? agent.unregister()
        }
        if SMAppService.mainApp.status == .enabled {
            try? SMAppService.mainApp.unregister()
        }
    }

    static func openLoginItemsSettings() {
        SMAppService.openSystemSettingsLoginItems()
    }
}

enum Shell {
    struct Result { let status: Int32; let stdout: String; let stderr: String }

    @discardableResult
    static func run(_ exe: String, _ args: [String], env: [String: String]? = nil,
                    cwd: String? = nil, timeout: TimeInterval = 60) -> Result {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = args
        if let env { p.environment = env }
        if let cwd { p.currentDirectoryURL = URL(fileURLWithPath: cwd) }
        let out = Pipe(), err = Pipe()
        p.standardOutput = out
        p.standardError = err
        do { try p.run() } catch {
            return Result(status: -1, stdout: "", stderr: "\(error)")
        }
        // 先读完管道再等待，避免输出超过管道缓冲时死锁
        var outData = Data(), errData = Data()
        let group = DispatchGroup()
        group.enter()
        DispatchQueue.global().async { outData = out.fileHandleForReading.readDataToEndOfFile(); group.leave() }
        group.enter()
        DispatchQueue.global().async { errData = err.fileHandleForReading.readDataToEndOfFile(); group.leave() }
        let deadline = Date().addingTimeInterval(timeout)
        while p.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
        if p.isRunning { p.terminate() }
        group.wait()
        p.waitUntilExit()
        return Result(status: p.terminationStatus,
                      stdout: String(decoding: outData, as: UTF8.self),
                      stderr: String(decoding: errData, as: UTF8.self))
    }
}
