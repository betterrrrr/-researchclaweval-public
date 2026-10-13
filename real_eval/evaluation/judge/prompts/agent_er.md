## ER —— 执行稳健性

### 枚举错误事件（口径写死，不要自己判断算不算）

在 `e2e.log` 里找**全部**符合下列**任一**条件的行，每条作为一个候选事件：

1. `stderr_text` 字段非空（不含空白）
2. 出现 `ERROR` / `Traceback` / `Exception` / `FAILED` / `failed` 的行
3. 出现 `timeout` / `Connection refused` / `No such file` 的行
4. `"exit_code"` 的值不是 0
5. `warning` / `WARN` 行**且**在下文中能找到由它引起的具体后果（某阶段没跑成、某产物没产出）

**不要**把这些算进去：正常提示与进度输出；只提到某种可选组件「未检测到」但没有造成任何后果的行；
同一根因的重复堆栈（同一根因只计 1 次，取**首次出现**那条）。

每个事件都要从日志里**逐字抄一段原文**（含时间戳或字段名）。

### 给每个事件判定处置

- `disposition`：`recovered_verified`（后续日志能证明已处理且**结果被验证**）/
  `recovered_unverified`（执行得以继续但**没有**验证）/ `unrecovered`（被识别记录但从未修复）/
  `ignored`（完全没被提及或处理）
- `impact`：`none` / `partial`（影响了部分产物或结论）/ `cascading`（整个执行无法继续）
