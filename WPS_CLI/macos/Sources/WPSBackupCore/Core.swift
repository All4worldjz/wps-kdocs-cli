import Foundation

// MARK: - 常量

public enum AppConstants {
    public static let bundleID = "cc.all4world.wpsbackup"
    /// 旧 SMAppService agent（已弃用：ad-hoc 签名下 launchd 固定 cdhash 约束，重建后被拒绝启动）
    public static let smAgentPlistName = "cc.all4world.wpsbackup.agent.plist"
    /// 经典 LaunchAgent（~/Library/LaunchAgents）：每小时运行 runner
    public static let schedulerLabel = "cc.all4world.wpsbackup.scheduler"
    /// 经典 LaunchAgent：登录时打开菜单栏 App（异常通知由 GUI 发出）
    public static let loginLabel = "cc.all4world.wpsbackup.login"
    public static let legacyLabel = "com.wps.backup"
    /// agent 每小时触发一次；超过该时长未见心跳视为 agent 未运行
    public static let heartbeatStaleSeconds: TimeInterval = 3 * 3600

    public static var supportDir: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/WPS Backup")
    }
    public static var settingsURL: URL { supportDir.appendingPathComponent("settings.json") }
}

// MARK: - 设置

public struct AppSettings: Codable, Equatable {
    public var engineRoot: String
    public var pythonPath: String
    public var scheduleHour: Int
    public var workers: Int
    public var exportDocx: Bool
    /// WPS Office 本地缓存扫描：需“完全磁盘访问权限”，默认关闭（airpage 已覆盖 Markdown + docx）
    public var cacheScan: Bool
    public var runTimeoutHours: Int

    public static func defaults(engineRoot: String) -> AppSettings {
        AppSettings(engineRoot: engineRoot,
                    pythonPath: "/opt/homebrew/opt/python@3.14/bin/python3.14",
                    scheduleHour: 20, workers: 4, exportDocx: true, cacheScan: false,
                    runTimeoutHours: 6)
    }

    public static func load(from url: URL = AppConstants.settingsURL, defaultEngineRoot: String) -> AppSettings {
        guard let data = try? Data(contentsOf: url),
              let s = try? JSONDecoder().decode(AppSettings.self, from: data) else {
            return defaults(engineRoot: defaultEngineRoot)
        }
        return s
    }

    public func save(to url: URL = AppConstants.settingsURL) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        try enc.encode(self).write(to: url, options: .atomic)
    }
}

// MARK: - 引擎运行环境（runner 与 GUI 共用，保证两者环境一致）

public struct EngineEnvironment {
    public let settings: AppSettings
    public let home: String

    public init(settings: AppSettings, home: String = NSHomeDirectory()) {
        self.settings = settings
        self.home = home
    }

    public var stateDir: String { settings.engineRoot + "/wps_backup_state" }
    public var backupDir: String { settings.engineRoot + "/wps_backup_data" }
    public var script: String { settings.engineRoot + "/wps_backup.py" }

    /// launchd 默认 PATH 不含 ~/.local/bin；/usr/local/bin 下是旧版 wps365-cli v0.1.0，刻意排除
    public var variables: [String: String] {
        [
            "PATH": "\(home)/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": home,
            "LANG": "en_US.UTF-8",
            "PYTHONIOENCODING": "utf-8",
            "WPS_BACKUP_HOUR": String(settings.scheduleHour),
            "WPS_BACKUP_WORKERS": String(settings.workers),
            "WPS_AIRPAGE_EXPORT_DOCX": settings.exportDocx ? "1" : "0",
            "WPS_OTL_CACHE_SCAN": settings.cacheScan ? "1" : "0",
            "WPS_BACKUP_RUN_TIMEOUT": String(settings.runTimeoutHours * 3600),
        ]
    }

    public func arguments(_ command: [String]) -> [String] {
        [settings.pythonPath, script] + command
    }
}

// MARK: - 引擎状态模型（status --json / progress.json）

public enum HealthLevel: String, Codable, Comparable {
    case ok, warn, error
    private var rank: Int { self == .ok ? 0 : (self == .warn ? 1 : 2) }
    public static func < (a: HealthLevel, b: HealthLevel) -> Bool { a.rank < b.rank }
}

public struct Health: Codable, Equatable {
    public var level: HealthLevel
    public var reasons: [String]
    public init(level: HealthLevel, reasons: [String]) { self.level = level; self.reasons = reasons }
}

public struct RunProgress: Codable, Equatable {
    public var running: Bool?
    public var pid: Int?
    public var trigger: String?
    public var startedAt: String?
    public var phase: String?
    public var done: Int?
    public var total: Int?
    public var current: String?

    enum CodingKeys: String, CodingKey {
        case running, pid, trigger, phase, done, total, current
        case startedAt = "started_at"
    }

    public var fraction: Double {
        guard let t = total, t > 0 else { return 0 }
        return Double(done ?? 0) / Double(t)
    }
}

public struct LastRun: Codable, Equatable {
    public var trigger: String?
    public var startedAt: String?
    public var finishedAt: String?
    public var exitCode: Int
    public var counts: [String: Int]
    public var errorCount: Int?
    public var errors: [String]?

    enum CodingKeys: String, CodingKey {
        case trigger, counts, errors
        case startedAt = "started_at", finishedAt = "finished_at"
        case exitCode = "exit_code", errorCount = "error_count"
    }
}

public struct Heartbeat: Codable, Equatable {
    public var at: String
    public init(at: String) { self.at = at }
}

public struct CLIInfo: Codable, Equatable {
    public var path: String?
    public var found: Bool?
    public var version: String?
}

public struct AuthInfo: Codable, Equatable {
    public var status: String?
    public var refreshable: Bool?
    public var refreshTokenExpiresAt: String?
    public var airpageScope: Bool?
    enum CodingKeys: String, CodingKey {
        case status, refreshable
        case refreshTokenExpiresAt = "refresh_token_expires_at", airpageScope = "airpage_scope"
    }
}

public struct SnapshotInfo: Codable, Equatable {
    public var snapshotCount: Int?
    public var totalSize: Int64?
    public var lastBackupAt: String?
    enum CodingKeys: String, CodingKey {
        case snapshotCount = "snapshot_count", totalSize = "total_size", lastBackupAt = "last_backup_at"
    }
}

public struct EngineStatus: Codable, Equatable {
    public var running: Bool
    public var progress: RunProgress?
    public var lastRun: LastRun?
    public var lastSuccessAt: String?
    public var heartbeat: Heartbeat?
    public var scheduleHour: Int?
    public var nextRunAt: String?
    public var cli: CLIInfo?
    public var auth: AuthInfo?
    public var health: Health
    public var snapshot: SnapshotInfo?
    public var backupDir: String?
    public var logFile: String?

    enum CodingKeys: String, CodingKey {
        case running, progress, heartbeat, cli, auth, health, snapshot
        case lastRun = "last_run", lastSuccessAt = "last_success_at"
        case scheduleHour = "schedule_hour", nextRunAt = "next_run_at"
        case backupDir = "backup_dir", logFile = "log_file"
    }

    public static func decode(_ data: Data) throws -> EngineStatus {
        try JSONDecoder().decode(EngineStatus.self, from: data)
    }
}

// MARK: - 时间解析（引擎写入本地时间 ISO8601，可能带或不带时区）

public enum ISO8601Local {
    public static func parse(_ s: String?) -> Date? {
        guard let s else { return nil }
        let withTZ = ISO8601DateFormatter()
        withTZ.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = withTZ.date(from: s) { return d }
        withTZ.formatOptions = [.withInternetDateTime]
        if let d = withTZ.date(from: s) { return d }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        for fmt in ["yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd HH:mm:ss"] {
            f.dateFormat = fmt
            if let d = f.date(from: s) { return d }
        }
        return nil
    }
}

// MARK: - 健康度合并（引擎健康 + agent 注册状态 + 心跳）

public enum AgentState: Equatable {
    case enabled, requiresApproval, notRegistered, notFound, spawnFailed, unknown
}

// MARK: - 经典 LaunchAgent plist 与 launchctl 输出解析

public enum LaunchAgentPlist {
    public static func scheduler(runnerPath: String) throws -> Data {
        try encode([
            "Label": AppConstants.schedulerLabel,
            "ProgramArguments": [runnerPath, "scheduled"],
            // 每小时整点触发；引擎判断是否到点/是否需重试。睡眠错过的触发在唤醒后补一次
            "StartCalendarInterval": ["Minute": 0],
            "RunAtLoad": false,
            "ProcessType": "Standard",
        ])
    }

    public static func loginItem(appPath: String) throws -> Data {
        try encode([
            "Label": AppConstants.loginLabel,
            "ProgramArguments": ["/usr/bin/open", "-a", appPath],
            "RunAtLoad": true,
        ])
    }

    static func encode(_ dict: [String: Any]) throws -> Data {
        try PropertyListSerialization.data(fromPropertyList: dict, format: .xml, options: 0)
    }
}

/// `launchctl print gui/<uid>/<label>` 输出（未加载时为 nil）→ agent 状态
public func parseAgentState(printOutput: String?, disabled: Bool) -> AgentState {
    if disabled { return .requiresApproval }
    guard let out = printOutput else { return .notRegistered }
    if out.contains("spawn failed") || out.contains("OS_REASON_CODESIGNING") { return .spawnFailed }
    return .enabled
}

/// `launchctl print-disabled gui/<uid>` 中该 label 是否被禁用（用户在“登录项”中关闭）
public func isDisabled(label: String, printDisabledOutput: String) -> Bool {
    printDisabledOutput.split(separator: "\n").contains {
        $0.contains("\"\(label)\"") && $0.contains("=> disabled")
    }
}

public func mergeHealth(engine: EngineStatus?, agent: AgentState, now: Date = Date(),
                        engineError: String? = nil) -> Health {
    var errors: [String] = []
    var warns: [String] = []

    switch agent {
    case .requiresApproval:
        errors.append("定时任务已被关闭：请在“系统设置 → 通用 → 登录项”中允许，或点击“启用定时备份”")
    case .notRegistered, .notFound:
        errors.append("定时任务未安装：点击“启用定时备份”")
    case .spawnFailed:
        errors.append("定时任务无法启动（launchd 拒绝），点击“启用定时备份”重新安装")
    case .unknown:
        warns.append("无法确认定时任务状态")
    case .enabled:
        break
    }

    guard let engine else {
        errors.append("无法读取备份引擎状态：\(engineError ?? "未知错误")")
        return Health(level: .error, reasons: errors + warns)
    }

    if agent == .enabled, let hb = ISO8601Local.parse(engine.heartbeat?.at),
       now.timeIntervalSince(hb) > AppConstants.heartbeatStaleSeconds {
        warns.append("定时任务已超过 3 小时未触发（Mac 睡眠或 agent 异常）")
    }

    switch engine.health.level {
    case .error: errors.append(contentsOf: engine.health.reasons)
    case .warn: warns.append(contentsOf: engine.health.reasons)
    case .ok: break
    }
    let level: HealthLevel = !errors.isEmpty ? .error : (!warns.isEmpty ? .warn : .ok)
    return Health(level: level, reasons: errors + warns)
}
