# JiaRu 项目长期记忆

## 远端推送权限（2026-08-29 实测）

- 远端为 `https://github.com/yaoyinyu/JiaRu.git`，分支 `master`，上游 `origin/master`。
- 本代理无法自行推送，三条通道均不通：本机环境变量 `GITHUB_API_KEY` 身份为 `yaoyinyu` 但对本仓库只有只读权限（push 返回 403）；`~/.ssh/id_ed25519.pub` 未授权给 GitHub（`ssh -T` 返回 `Permission denied (publickey)`）；Git Credential Manager 在无 TTY 环境无法弹窗取凭据（PowerShell 侧同样静默失败）。
- 因此默认流程为：本地用中文提交信息建好提交后，推送交给用户在自己的终端执行。不要反复重试远端写入，也不要为此改写 remote 地址。
- 若确需代理侧推送，必须先取得用户专门提供、且具备本仓库写权限的 PAT；使用一次性 askpass 脚本注入（Windows 下 `GIT_ASKPASS` 必须给 `C:/...` 形式路径，`/c/...` 形式 git 无法 spawn），用完立即删除，令牌不得写入命令行参数或仓库文件。
