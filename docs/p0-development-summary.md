# gayoj Phase 0 开发后期总结

> 日期：2026-05-23  
> 范围：P0-01 至 P0-05 工程基线加固  
> 当前技术栈：FastAPI + Vue 3 + TypeScript + 客观题离线 CLI

## 1. 总体结论

Phase 0 已完成工程基线加固，当前仓库具备稳定的后端测试、前端类型检查、API 回归脚本、OpenAPI 静态导出和统一环境变量入口。P0 的目标不是实现真实代码沙箱，而是让后续 P1 数据层迁移、P4 在线评测 worker、P5 客观题规则增强等任务有可重复验证的基础。

当前代码题仍保持硬性边界：Web、API、CLI 不在本地执行用户代码。现有 `submit-code` 流程只写入在线评测队列状态，不编译、不运行、不本地判定用户提交。真实编译、运行、资源限制和测试点聚合应在后续 P4 的 judge worker 中实现。

## 2. P0 交付清单

| 任务 | 状态 | 主要输出 | 验收入口 |
| --- | --- | --- | --- |
| P0-01 后端测试框架 | 已完成 | `apps/api/tests` | `npm run check:api` |
| P0-02 前端类型检查 | 已完成 | `npm run typecheck`、`vue-tsc` 配置 | `npm run typecheck` |
| P0-03 API 回归脚本 | 已完成 | `scripts/smoke-api.ps1`、`npm run smoke:api` | 登录、题库、提交、题单、通知全链路 |
| P0-04 OpenAPI 导出 | 已完成 | `api/openapi.json`、`scripts/export-openapi.py` | `npm run check:openapi` |
| P0-05 环境变量梳理 | 已完成 | `.env.example`、本地/Compose 配置说明 | `apps/api/tests/test_env_contract.py` |

## 3. 当前质量基线

必须保留的常规验证命令：

```powershell
npm run check:api
npm run typecheck
npm run build:web
npm run check:openapi
npm run smoke:api
py -3.12 tools/offline-cli/gayoj_offline.py --help
```

当前测试覆盖重点：

- 后端 API smoke：登录、用户信息、普通题面不泄露 `judge_config`、客观题服务端判分、代码题进入在线评测队列路径、离线包只含客观题、CLI 拒绝代码题判分。
- API 回归脚本：登录、题库、题面、客观题提交、代码题提交、我的提交、题单、通知读取与标记已读。
- OpenAPI：`api/openapi.json` 与 FastAPI `app.openapi()` 一致，并可与 `/api/openapi.json` 对比。
- 环境变量：`.env.example` 覆盖本地、CLI、smoke、Compose 所需变量，且 `.env` 被忽略。

## 4. 硬性边界复核

| 边界 | 当前状态 | 说明 |
| --- | --- | --- |
| 代码题不得在 API、Web、CLI 本地执行 | 保持 | API 只写入在线评测队列状态，不启动编译器、解释器或本地判题逻辑；CLI 直接拒绝代码题判分 |
| 普通题面接口不得返回客观题 `judge_config` | 保持 | `GET /api/v1/problems/{id}` 对未授权普通访问使用 `response_model_exclude_none=True` |
| CLI 只允许填空题、单选题、多选题 | 保持 | `judge()` 遇到 `code` 类型会退出 |
| 保持 FastAPI + Vue 3 + TypeScript | 保持 | P0 只加固工程入口，没有迁移框架 |
| 存储结构兼容 `apps/api/storage/dev-db.json` | 保持 | P0 未改变 JSON 数据结构 |

## 5. 代码评测机规格基线

以下规格作为后续 P4 在线 judge worker 的实现基线。P0 不在 API、Web 或 CLI 中执行这些命令。

### 5.1 运行环境

- 系统：Ubuntu Server 24.04
- C/C++：gcc/g++ 14.2.0
- Python：3.12.x
- Java：OpenJDK 21.x
- 输入：stdin，输出：stdout
- 禁止行为：评测程序不得读写文件或使用其他输入输出通道，违规应判为 `Runtime Error`

### 5.2 编译与运行命令

C:

```bash
gcc -std=c17 -O2 -Wall -Wextra -DONLINE_JUDGE -static -Wl,--no-relax -Wl,--no-pie -mcmodel=medium -o Main Main.c
```

C++:

```bash
g++ -std=c++17 -O2 -Wall -Wextra -DONLINE_JUDGE -static -Wl,--no-relax -Wl,--no-pie -mcmodel=medium -o Main Main.cpp
```

Java:

```bash
javac -J-Xms1024M -J-Xmx1024M -J-Xss64M -encoding UTF-8 Main.java
java -Dfile.encoding=UTF-8 -XX:+UseSerialGC -Xss64M -Xms1024M -Xmx<题目内存限制+512M> -cp . Main
```

Python:

```bash
python3 -m py_compile Main.py
python3 Main.py
```

实现注意事项：

- `-Wall -Wextra` 用于暴露常见警告和潜在问题。
- `-static` 生成静态链接可执行文件。
- `-Wl,--no-relax -Wl,--no-pie -mcmodel=medium` 用于降低静态链接重定位问题。
- `-DONLINE_JUDGE` 作为评测环境预处理宏。
- Java、Python 需要在题目时间/内存限制基础上设置额外运行开销，具体数值由后端配置和 worker 调度策略决定。

### 5.3 输入输出规范示例

多组 `a b` 求和直到文件末尾，选手程序应从标准输入读取、向标准输出写入。

C:

```c
#include <stdio.h>
int main() {
    int a, b;
    while (scanf("%d %d", &a, &b) != EOF) {
        printf("%d\n", a + b);
    }
    return 0;
}
```

C++:

```cpp
#include <iostream>
using namespace std;
int main() {
    int a, b;
    while (cin >> a >> b) {
        cout << a + b << endl;
    }
    return 0;
}
```

Python:

```python
import sys
for line in sys.stdin:
    a, b = line.split()
    print(int(a) + int(b))
```

Java:

```java
import java.util.*;
public class Main {
    public static void main(String[] args) {
        Scanner cin = new Scanner(System.in);
        while (cin.hasNext()) {
            int a = cin.nextInt();
            int b = cin.nextInt();
            System.out.println(a + b);
        }
    }
}
```

### 5.4 Compile Error 常见原因

- `main` 返回值必须为 `int`，不得使用 `void main`。
- `for (int i = 0; ...)` 中声明的 `i` 不应在循环外继续使用。
- `itoa` 不是 ANSI C/C++ 标准函数。
- `__int64` 不是标准类型，64 位整数应使用 `long long`。
- 本地 MSVC 与 GNU 编译器存在差异，后续题面和帮助文档应以 Ubuntu 24.04 judge worker 为准。

### 5.5 评测结果枚举

| 结果 | 含义 |
| --- | --- |
| Accepted | 程序正确编译执行并通过全部数据 |
| Pending | 程序已录入数据库，等待评测 |
| Pending Rejudge | 程序等待重测 |
| Compiling | 程序正在被评测机编译 |
| Presentation Error | 逻辑正确但输出格式不完全一致 |
| Wrong Answer | 存在测试数据结果不一致 |
| Time Limit Exceeded | 超出题目时间限制 |
| Memory Limit Exceeded | 超出题目内存限制 |
| Output Limit Exceeded | 输出远超答案长度或疑似死循环 |
| Runtime Error | 段错误、浮点异常、非法内存访问、禁止函数或禁止文件 I/O 等 |
| Compile Error | 评测机无法编译程序 |
| Judge Error | 评测机遇到非预期情况，需要管理员处理 |

## 6. 后续开发建议

优先顺序建议：

1. P5-01：客观题规则引擎单测，确保在线与 CLI 判分一致。
2. P3-01：题目 CRUD 完整表单，为题库运营补齐管理入口。
3. P2-01：权限码模型，把粗粒度角色判断演进为权限码。
4. P1-01：仓储层抽象，为 PostgreSQL 迁移做准备。
5. P4-01/P4-02：提交队列抽象和 judge worker 服务，把当前代码题模拟评测替换为真实在线评测链路。

进入 P4 前必须先明确：

- worker 与 API 进程隔离，不共享高权限进程。
- worker 使用临时目录执行，并在评测结束后清理。
- 沙箱默认禁网，限制 CPU、内存、进程数和输出大小。
- 编译命令必须按本总结第 5 节规格执行。
- 用户源码不得写入仓库目录，也不得在 API、Web、CLI 本地执行。

## 7. 已知剩余风险

- 当前代码题结果仍是模拟在线评测回写，不具备真实编译、沙箱、测试点聚合能力。
- `docker compose` 在当前机器未能实测，因为 Docker CLI 未安装或未加入 PATH；P0 仅通过静态测试保证 Compose 变量契约。
- `npm run smoke:api` 会向开发 JSON 存储追加提交记录和通知，并可能标记通知已读；它适合开发环境回归，不应直接对生产数据运行。
- `judge_config` 在开发 JSON 中仍与题目对象同文件存储，普通接口已隔离返回，但后续 P1/P1-05 应拆分或加密存储。

