# JMComic Web

基于 [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) 的本地 Web 管理界面。

保留原有漫画下载逻辑，只额外提供一个轻量级网页端，用于：

- 批量下载
- 下载历史管理
- 封面预览
- 重新下载
- 下载状态查看

---

# 技术栈

- Python
- SQLite
- `http.server`
- 原生 HTML / CSS / JavaScript
- `jmcomic` 下载核心

---

# 快速开始

下面的命令都需要在 **终端（PowerShell / CMD）** 中执行。

不要在 Python 的 `>>>` 交互界面中输入。

如果你看到：

```text
>>>
```

说明已经进入 Python 解释器。请先输入：

```python
exit()
```

或者按：

```text
Ctrl + Z
回车
```

退出后再继续。

---

## 1. 安装 Python

推荐使用：

- Python 3.12+

安装完成后，确认以下命令可用：

```shell
python --version
```

如果 `python` 不可用，也可以使用：

```shell
py --version
```

---

## 2. 进入项目目录

假设项目位于：

```text
D:\JMComic-Crawler-Python
```

执行：

```shell
cd D:\JMComic-Crawler-Python
```

确保当前目录下能看到：

```text
pyproject.toml
src/
```

---

## 3. 创建虚拟环境（推荐）

### PowerShell

```shell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### CMD

```shell
py -3 -m venv .venv
.\.venv\Scripts\activate.bat
```

激活成功后，终端前面通常会出现：

```text
(.venv)
```

---

## 4. 安装项目

优先执行：

```shell
python -m pip install -e .
```

如果没有 `python` 命令：

```shell
py -3 -m pip install -e .
```

---

## 5. 启动 Web 服务

优先执行：

```shell
python -m jmcomic_web
```

如果没有 `python` 命令：

```shell
py -3 -m jmcomic_web
```

启动成功后，打开浏览器访问：

```text
http://127.0.0.1:5000
```

---

# 使用说明

## 批量下载

在首页输入漫画 ID：

```text
123456
654321
111111
```

一行一个。

点击「开始下载」后，页面会实时显示：

- 下载进度
- 成功 / 失败状态
- 错误信息

---

## 下载历史

历史页面支持：

- 查看下载记录
- 查看封面
- 重新下载
- 查看下载状态

---

# 数据存储

默认数据保存在：

```text
instance/
```

目录结构：

```text
instance/
├─ jmcomic_web.sqlite3
└─ downloads/
```

其中：

- `jmcomic_web.sqlite3`：SQLite 数据库
- `downloads/`：漫画下载目录

---

# 启动参数

可以自定义监听地址、端口、数据库位置和下载目录。

示例：

```shell
python -m jmcomic_web ^
  --host 127.0.0.1 ^
  --port 5000 ^
  --db-path D:\data\jmcomic_web.sqlite3 ^
  --base-dir D:\data\downloads
```

---

# 配置文件

也可以使用配置文件启动：

```shell
python -m jmcomic_web --config D:\jmcomic-web.yml
```

环境变量：

```text
JM_WEB_CONFIG_PATH
```

用于指定默认配置文件路径。

---

# 关于 `jmcomic-web` 命令

安装后有些系统会生成：

```shell
jmcomic-web
```

快捷命令。

如果系统提示：

```text
'jmcomic-web' 不是内部或外部命令
```

属于正常情况，不影响使用。

推荐始终使用：

```shell
python -m jmcomic_web
```

或者：

```shell
py -3 -m jmcomic_web
```
