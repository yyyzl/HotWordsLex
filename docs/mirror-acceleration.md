# HotWords 镜像加速说明

## 目标

为国内网络环境提供稳定拉取能力。主文件固定为：

- `output/hotwords_latest.txt`
- `output/hotwords_latest.json`

每次采集后自动生成镜像清单：

- `output/hotwords_latest_endpoints.json`

## 回退策略

采用顺序回退（ordered-fallback）：

1. `gh-proxy.org`
2. `hk.gh-proxy.org`
3. `cdn.jsdelivr.net`
4. `raw.githubusercontent.com`（直连兜底）
5. `cdn.gh-proxy.org`
6. `edgeone.gh-proxy.org`

外部项目按顺序请求，首个成功即使用。

## 配置方式

采集任务在运行时通过环境变量生成目标仓库 URL：

- `HOTWORDS_PUBLISH_REPO`：`owner/repo`
- `HOTWORDS_PUBLISH_REF`：分支名（如 `main`）

GitHub Actions 已自动注入：

- `${{ github.repository }}`
- `${{ github.ref_name }}`

## 注意事项

- 代理镜像属于第三方服务，可能不稳定。
- 建议外部项目缓存最近一次可用结果，并保留直连兜底。
