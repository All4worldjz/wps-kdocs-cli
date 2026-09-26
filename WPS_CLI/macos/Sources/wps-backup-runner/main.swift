// wps-backup-runner — 由 App 内嵌的 launchd agent（SMAppService）每小时执行。
// 读取 App 设置，构造与 GUI 相同的环境变量，exec 进入 Python 引擎：
//   python3 wps_backup.py scheduled
// 引擎自行判断是否到点/是否有“立即备份”请求，并写入 last_run.json 等契约文件。
import Foundation
#if canImport(WPSBackupCore)
import WPSBackupCore
#endif

let defaultRoot = Bundle.main.object(forInfoDictionaryKey: "WPSEngineRoot") as? String ?? ""
let settings = AppSettings.load(defaultEngineRoot: defaultRoot)
let env = EngineEnvironment(settings: settings)

// launchd agent 的 stdout/stderr 无处可去：追加到状态目录，便于排查
let logPath = env.stateDir + "/agent_runner.log"
try? FileManager.default.createDirectory(atPath: env.stateDir, withIntermediateDirectories: true)
let fd = open(logPath, O_WRONLY | O_CREAT | O_APPEND, 0o644)
if fd >= 0 {
    dup2(fd, STDOUT_FILENO)
    dup2(fd, STDERR_FILENO)
    close(fd)
}

let runnerVersion = "1.0.3"

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write(Data("\(Date()) wps-backup-runner \(runnerVersion): \(msg)\n".utf8))
    exit(1)
}

guard FileManager.default.isExecutableFile(atPath: settings.pythonPath) else {
    fail("找不到 Python: \(settings.pythonPath)")
}
guard FileManager.default.fileExists(atPath: env.script) else {
    fail("找不到引擎脚本: \(env.script)")
}

let command = CommandLine.arguments.count > 1 ? Array(CommandLine.arguments.dropFirst()) : ["scheduled"]
for (k, v) in env.variables { setenv(k, v, 1) }
setenv("WPS_BACKUP_NO_CONSOLE", "1", 1)  // 日志已写入轮转的 backup.log，避免在 agent_runner.log 重复
FileManager.default.changeCurrentDirectoryPath(settings.engineRoot)

let argv = env.arguments(command).map { strdup($0) } + [nil]
execv(settings.pythonPath, argv)
fail("execv 失败: \(String(cString: strerror(errno)))")
