# bet365-scraper, scrape Bet365 live score, include soccer and basketball, score and odds.
# bet365 爬虫，抓取websocket数据，可以获取bet365的滚球，包括队伍信息实时比分、实时赔率。

# English
#### Function:
Retrieve Live Match Information from Bet365 (football, basketball and other in-play sports parsed from `OVInPlay`).

#### Features:
- Intercept Bet365 WebSocket messages in the browser and expose them as a local HTTP API.
- Parse in-play events for all sports found in `OVInPlay` (`C{sportId}A…`), with richer fields (score, time, period, markets/odds when present).
- Football tech stats from topic `OVS1` / `OVSF*` (corners, cards, etc.).
- Language suffix auto-detected from `GamingContext.languageId` (no manual edit needed).

#### Principle:
Intercept WebSocket messages from Bet365’s webpage in the browser and send the data to an HTTP API service.

#### Data refresh rules:
1. On full snapshot `\x14OVInPlay_…` → clear previous match data, then full parse.
2. On full snapshot `\x14OVS1` (payload contains `|CL;ID=1;IT=OVS1;`) → clear football stats, then full parse.
3. Incremental `\x15…` messages (`U` / `I` / `D`) update matches or `OVSF{fixtureId}` stats in place.
4. Football stats are keyed by fixture id (`OI` / `OVSF{id}`) and re-attached after an `OVInPlay` refresh until the next `OVS1`.

#### Deployment and Installation Steps:
1. Install the Chrome extension `chrome_extention` on Chrome.

2. Set up a Python environment and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   (`flask`, `flask-cors`, `pytz`)

3. Run `local_api.py` (for better HTTP performance, you may deploy a dedicated web server).

4. Open the browser extension panel and configure the upload URL. Default:
   `http://127.0.0.1:8485/data`

5. Open the Bet365 live / in-play page in your browser. Keep the page open so WebSocket data keeps flowing.

**Note:** Football tech stats (`OVS1` / `/soccer/stats`) are only pushed after you click the **Stats** button above the in-play match list on the Bet365 page. Without that, `/live` may show empty or zero stats.

#### How to Use the API:
1. All live matches (GET):

`http://127.0.0.1:8485/live`

2. Football matches (GET):

`http://127.0.0.1:8485/live?sport=1`

3. Basketball matches (GET):

`http://127.0.0.1:8485/live?sport=18`

4. Sport list & counts (GET):

`http://127.0.0.1:8485/sports`

5. Football tech stats only (GET):

`http://127.0.0.1:8485/soccer/stats`

6. WebSocket raw parsed store (GET) / receive from extension (POST):

`http://127.0.0.1:8485/data`

7. Soccer Goal Line (remote sample, GET)：

`http://124.156.195.77:8365/b365/soccer/test/oneHd2allEv/C1-G15?lang=en`

#### Football stats fields (`/soccer/stats` → `stats`):
| Source | Name |
|--------|------|
| S0 | Goal |
| S1 | Corner |
| S2 | YellowCard |
| S3 | RedCard |
| S4 | ThrowIn |
| S5 | FreeKick |
| S6 | GoalKick |
| S7 | Penalty |
| S8 | Substitution |

Each value is `{ "home": n, "away": n }`. Empty source values become `null`. Matches not yet started often show `0`.

#### Common sport ids:
| id | sport |
|----|--------|
| 1 | Football |
| 13 | Tennis |
| 16 | Baseball |
| 18 | Basketball |
| … | see `/sports` for whatever is currently live |

### Any question contact
This project can only capture limited data, more data please contact

Telegram: https://t.me/JoeBili

# 中文
#### 功能：
获取 bet365 滚球比赛信息（足球、篮球及其他 `OVInPlay` 中出现的运动），包括队伍、时间、比分、盘口赔率；足球另有技术统计。

#### 特点：
- 浏览器拦截 WebSocket，本地 HTTP 读取。
- 按 `C{sportId}A…` 动态收录各运动 EV；`/live` 输出比分、时间、阶段、markets 等。
- 足球技术统计来自 `OVS1` / `OVSF*`。
- 语言后缀由页面 `GamingContext.languageId` 自动识别（无需再改代码里的语言变量）。

#### 原理：
拦截浏览器中 bet365 网页的 websocket 消息，通过 http 发送到接口服务。

#### 数据刷新规则：
1. 收到全量 `\x14OVInPlay_…` → 清空原有比赛信息，再全量解析。
2. 收到全量 `\x14OVS1`（内容含 `|CL;ID=1;IT=OVS1;`）→ 清空足球统计，再全量解析。
3. 增量 `\x15…`（`U` / `I` / `D`）就地更新比赛或 `OVSF{fixtureId}` 统计。
4. 足球统计按赛事 id（`OI` / `OVSF{id}`）存档；`OVInPlay` 刷新后会重新挂回，直到下一包 `OVS1` 覆盖。

#### 部署和安装步骤：
1. 在 Chrome 上安装浏览器插件 `chrome_extention`。

2. 部署 Python 环境，安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
   （`flask`、`flask-cors`、`pytz`）

3. 运行 `local_api.py`；如需更高性能可自行部署专用 web。

4. 在浏览器插件面板配置 upload url，默认：
   `http://127.0.0.1:8485/data`

5. 打开 bet365 滚球 / 进行中页面，保持页面打开以持续收包。

**说明：** 足球技术统计（`OVS1` / `/soccer/stats`）需要先点击网页滚球列表**上方的「统计信息」按钮**，页面才会下发统计数据；未点击时 `/live` 里的 `stats` 可能为空或全 0。

#### 如何调用接口:
1. 全部滚球比赛 (GET)：

`http://127.0.0.1:8485/live`

2. 足球 (GET)：

`http://127.0.0.1:8485/live?sport=1`

3. 篮球 (GET)：

`http://127.0.0.1:8485/live?sport=18`

4. 当前运动列表与场次 (GET)：

`http://127.0.0.1:8485/sports`

5. 仅足球技术统计 (GET)：

`http://127.0.0.1:8485/soccer/stats`

6. WebSocket 解析后的原始仓库 (GET) / 插件上报 (POST)：

`http://127.0.0.1:8485/data`

7. 足球大小球指数（远程示例，GET）：

`http://124.156.195.77:8365/b365/soccer/test/oneHd2allEv/C1-G15`

#### 足球技术统计字段（`/soccer/stats` 的 `stats`）：
| 原始 | 名称 |
|------|------|
| S0 | Goal |
| S1 | Corner |
| S2 | YellowCard |
| S3 | RedCard |
| S4 | ThrowIn |
| S5 | FreeKick |
| S6 | GoalKick |
| S7 | Penalty |
| S8 | Substitution |

每项为 `{ "home": n, "away": n }`；源字段为空则为 `null`。未开赛或暂无事件常见为 `0`。

#### 常见运动 id：
| id | 运动 |
|----|------|
| 1 | 足球 |
| 13 | 网球 |
| 16 | 棒球 |
| 18 | 篮球 |
| … | 以 `/sports` 当前列表为准 |

### 问题交流
此项目只能抓取有限数据，更多数据联系

Telegram: https://t.me/JoeBili

企鹅q：3403027828
