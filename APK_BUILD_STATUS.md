# APK 构建状态

当前 Windows 环境未安装 `buildozer`、Java、Gradle、Android SDK/NDK，WSL/Ubuntu 也尚未完成可用初始化，因此本机暂时无法直接生成真实 `.apk` 安装包。

更简单的生成方式已经加入项目：使用 GitHub Actions 云端构建。把项目上传到 GitHub 后，进入 `Actions`，运行 `Build Android APK` 工作流，构建完成后从 `Artifacts` 下载 APK。

本项目已经提供：

- `main.py`：新版精美 UI + 完整文件速传功能。
- `buildozer.spec`：Android APK 打包配置。
- `build_apk_linux.sh`：Linux / WSL 下的一键构建脚本。
- `.github/workflows/build-apk.yml`：GitHub Actions 云端 APK 构建流程。

在安装好 Linux/WSL + Java + Android SDK/NDK + Buildozer 后，进入项目目录执行：

```bash
chmod +x build_apk_linux.sh
./build_apk_linux.sh
```

成功后 APK 会生成在：

```text
bin/*.apk
```
