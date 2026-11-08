# 发布 / 收录说明（PUBLISH）

> 目标：让这个节点能被 **ComfyUI-Manager** 搜到并一键装；条件成熟后同步到 **官方 Registry**（registry.comfy.org）。

## 一、已经就绪的部分

| 项 | 状态 |
|---|---|
| 公开仓库 | ✅ https://github.com/dxyliwei520/comfyui-dm-paraformer-asr |
| 包结构 | ✅ `__init__.py` / `requirements.txt` / `pyproject.toml`(含 `[tool.comfy]`) / `custom-node-list.json` / `LICENSE` / README(中英) |
| 节点命名 | ✅ 全部 `DM` 前缀（`DMASRTranscribe` / `DMASRFile` / `DMASRPayAmount` / `DMASRInfo`），分类 `DM/Audio` |
| 实机验证 | ✅ ComfyUI 0.42.1 加载成功 + `LoadAudio → DMASRTranscribe → DMASRPayAmount` 全链路 success |
| Manager 清单 | ✅ `custom-node-list.json`（`install_type: git-clone`，`nodename_pattern: ^DMASR`） |

## 二、用户怎么装（已可用，不需要 Registry）

**A. Manager → Install via Git URL**，填：

```
https://github.com/dxyliwei520/comfyui-dm-paraformer-asr
```

**B. 手动**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/dxyliwei520/comfyui-dm-paraformer-asr.git dm_paraformer_asr
<你的 python> -m pip install -r dm_paraformer_asr/requirements.txt
```

**C. 国内网络**（github.com 直连不通时）：把 `git clone` 地址换成镜像前缀，例如

```
https://ghproxy.net/https://github.com/dxyliwei520/comfyui-dm-paraformer-asr.git
```

模型不用额外下 —— 首次识别会自动从 `hf-mirror.com` 拉（82 MB）。

## 三、同步到官方 Registry（**剩下这一步必须浏览器登录一次**）

Registry 的发布凭据绑在 **你的 GitHub 账号**上，且**只能在网页里创建**（我这边没有 `gh` CLI、也没有 registry 的 API Key）：

1. 打开 https://registry.comfy.org ，用 GitHub（`dxyliwei520`）登录；
2. 首次会让你**创建 Publisher**（名字建议 `dm` 或 `dxyliwei520`）；
3. Publisher 页面里 **Create API Key**，复制；
4. 把 PublisherId（就是第 2 步那个 id）填进 `pyproject.toml`：

   ```toml
   [tool.comfy]
   PublisherId = "你的 PublisherId"     # ← 把 REPLACE_WITH_YOUR_PUBLISHER_ID 换掉
   DisplayName = "DM Paraformer ASR (离线中文语音转文字)"
   ```

5. 发布（二选一）：

   ```bash
   # 方式 A：comfy-cli
   pip install comfy-cli
   comfy node publish --token <第 3 步的 API Key>
   # 方式 B：直接打 API（不需要装 comfy-cli）
   curl -X POST https://api.comfy.org/nodes \
        -H "Authorization: <API Key>" -H "Content-Type: application/json" \
        -d @node.json     # 字段见 https://docs.comfy.org/registry/publishing
   ```

发布后 5~10 分钟，Manager 里搜 `DM Paraformer ASR` 就能装到。

## 四、给 Manager 官方清单提 PR（可选，非必须）

`ltdrdata/ComfyUI-Manager` 现在主推 Registry，PR 到它的 `custom-node-list.json` 已不常用；
如果还想提，直接把本仓库 `custom-node-list.json` 里的这一条追加进去即可：

```json
{
  "author": "dxyliwei520",
  "title": "DM Paraformer ASR (离线中文语音转文字 · 不占显存)",
  "reference": "https://github.com/dxyliwei520/comfyui-dm-paraformer-asr",
  "files": ["https://github.com/dxyliwei520/comfyui-dm-paraformer-asr/archive/refs/heads/main.zip"],
  "install_type": "git-clone",
  "description": "离线中文语音转文字：sherpa-onnx + Paraformer-zh-small（78MB int8），纯 CPU、不联网、不占显存。附带收款金额抽取节点。",
  "version": "1.0.0",
  "nodename_pattern": "^DMASR"
}
```

## 五、发版 checklist（以后每改一版）

1. 改 `pyproject.toml` 的 `version` + 本文件版本说明；
2. 本地 `python -m py_compile __init__.py asr.py amount.py`；
3. 用 `examples/api_audio_to_amount.json` 在 8189 上跑一遍（判据：`amount=1.28 cents=128`）；
4. `git tag v1.x.y && git push --tags`；
5. 需要上 Registry 的再跑 `comfy node publish --token <API Key> --changelog "..."`。

---

## 六、✅ 已发布（2026-11-08）

| 项 | 值 |
|---|---|
| Registry 节点 ID | **`dm-paraformer-asr`** |
| Registry 页面 | https://registry.comfy.org/nodes/dm-paraformer-asr |
| Publisher | **DM Studio**（id `dxyliwei520`）|
| 版本 | **1.0.0**（`NodeVersionStatusPending` —— 新 Publisher 首发会先挂起审核，通过后 Manager 里可搜到）|
| 包下载地址 | `https://cdn.comfy.org/dxyliwei520/dm-paraformer-asr/1.0.0/node.zip` |

### 发新版的固定动作（下次照抄，不用再问人）

```powershell
# 1) 改 pyproject.toml 的 version（如 1.0.1）
# 2) 提交推送
cd F:\dm-publish\comfyui-dm-paraformer-asr
git add -A; git commit -m "feat: ..."; git push origin main; git tag v1.0.1; git push --tags
# 3) 发布（token 在 C:\Users\liwei\.github\IDkey.txt 里，pat- 开头那串）
$env:PYTHONUTF8='1'          # ⚠️ 必须设：不然 comfy-cli 用 GBK 读 pyproject 会报 codec 错
& F:\dm-publish\.venv-comfy\Scripts\comfy.exe node publish --token <pat-...> --changelog "改了什么"
```

**两个坑（都踩过）**：
1. **不设 `PYTHONUTF8=1`** → `'gbk' codec can't decode byte 0xad`（读 UTF-8 的 pyproject 失败）。
2. **上传超时 ≠ 失败**：报 `Read timed out` 时**先去查** `https://api.comfy.org/nodes/dm-paraformer-asr/versions`；如果版本已在，就是**已经成功**了，别重复重试（再试只会报 `The node version already exists`）。
