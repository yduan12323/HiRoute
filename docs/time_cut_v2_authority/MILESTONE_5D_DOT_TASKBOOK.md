
## 任务名称

**M5-D — Deployable Exact Multi-Stop Planning and Publication-Ready Evaluation**

### 总目标

从执行时的 `origin/main` 新建开发分支，在不改变已经接受的 time-cut v2 决策语义的前提下，完成：

> 一个具有明确搜索域、独立可行初始解、可部署 Region 下界、成本可核算的路线查询接口和完整结果状态的多停靠求解器，并通过预注册开发集评估其计算收益。

**本轮完成到 M5-D 报告、代码提交和待审查 PR 为止。可以准备 holdout 协议和封存清单，但不得自动运行最终 holdout。**

---

## D0. 起点、工作区和权限

### D0.1 从当前 main 开发，不修改冻结生产验证目录

本任务书核对时的基线提交：

```text
1af12a96ca7de909f5971e49f118322117bf07ec
```

执行时先读取最新 `origin/main`，记录实际基线 SHA。若 `main` 已前移，必须比较新增改动：文档和证据整理可以记录后继续；若数学内核、数据契约或验收范围发生变化，应先确认新提交是否已有对应验收。

在**新的工作目录**中创建分支，例如：

```bash
git clone --branch main https://github.com/yduan12323/HiRoute.git HiRoute-m5d
cd HiRoute-m5d
git fetch origin main
BASE_SHA="$(git rev-parse origin/main)"
git switch -c dot/m5d-deployable "$BASE_SHA"
```

不得在已冻结的 `/home/dy/HiRoute/project` 生产验证工作区中执行拉取、切换分支或覆盖源码。不得自动合并 `main`、强推、改变仓库权限或删除历史记录。

### D0.2 首先阅读的现有材料

按语义与用途分别阅读，不把所有历史文件混为同时有效的规范：

| 用途 | 文件 |
|---|---|
| 当前验收范围 | `docs/MILESTONE_5_V_R12_FINAL_ACCEPTANCE.md` |
| 当前数学语义 | `docs/MILESTONE_5_TIME_CUT_THEORY_REVIEW_V2.md` |
| cut 与 witness 接口 | `docs/MILESTONE_5_TIME_CUT_CONTRACT_V2.md`、`docs/MILESTONE_5_TIME_CUT_PWA_DESIGN_V2.md` |
| 当前实现与有限域证据 | `docs/MILESTONE_5_V_FINAL_CANDIDATE_REVIEW.md` |
| 真实数据及可选合并表示边界 | `docs/MILESTONE_5_C32_RETAINED_ADMISSION.md`、真实 leg 契约 |
| 最初设计与应用边界 | `RESEARCH_SPEC_v0.2.md` |
| 环境与测试入口 | `ci/README.md`、当前 CI 脚本、环境锁文件 |

旧 B21-v0/v1 的错误定理和失败测试属于历史证据，**不能重新作为实现规则，也不能为了“全绿”删除或改写**。

### D0.3 基线检查

记录源码、配置、输入和环境指纹；运行当前接受的代码测试入口。把测试分成三个账本：

- 已接受前驱测试；
- 历史上已经被反驳的契约测试；
- 本轮新实现测试。

历史错误契约按其原意继续失败，不等于新代码回归；但其结果必须与已归档行为相符。任何**新的、未解释的失败**均须调查，不能通过全局跳过或修改预期掩盖。

**D0 交付：**基线 manifest、当前状态入口文档、测试分层清单。不要重跑已经封存的全部百万级证书生产。

---

## D1. 固定本轮求解问题，避免性能实验悄悄换题

### D1.1 保持以下语义

维持当前接受的：

\[
K(p)=(J,Q,H,\Pi),\qquad
J=T_{\mathrm{clock}}+\lambda_{\mathrm{stop}}H.
\]

维持连续充电、严格正充电动作、单个可选硬时间窗需求、C/S/CS、既定并行服务模型、time-cut 的构造性 witness 和同状态安全 reduction。

不得加入 SOC 网格、任意最小充电量、未证明的跨能量 dominance、启发式 frontier 截断、固定充到 80% 的精确动作限制，或把未达到的下确界当作可执行方案。

终端结果必须按**逐级已达到的最优面**求解：先处理 \(J\) 的最优值与达到性，再在达到的 \(J\)-最优面上处理 \(Q\)。不能只检查主目标是否达到。

### D1.2 每个结果必须说明“对哪个问题精确”

建议至少记录：

```text
graph_sha
site_universe_sha
selected_leg_contract
query_parameters_sha
representation_version
mobility_budget
depth_mode
depth_limit
candidate_restriction
```

明确区分：

| 搜索域 | 可用表述 |
|---|---|
| 选定 N 个 Site、固定 H_ref | 在该候选集和深度内精确 |
| 选定 N 个 Site、由 incumbent 推导深度 | 在该候选集内完成相关深度的精确搜索 |
| 完整合格 Site 集、相关深度证明完整 | 在声明的完整模型域内精确 |

不能把“小候选集内最优”写成“全图最优”。

同样，若保留 \(2C^*\) 移动成本上限，应把它作为**明确的查询限制**；不能一边利用它丢弃路线，一边声称对未限制的原问题精确。

### D1.3 退出状态

至少区分：

```text
attained_optimum
infimum_unattained_J
infimum_unattained_Q
infeasible_within_declared_domain
incumbent_search_failed
time_limit
memory_limit
verification_failed
```

超时不等于不可行；找到可行 incumbent 不等于找到最优解；未完成深度搜索不等于深度外没有改进方案。

---

## D2. 把 H4 验证器接成具有明确边界的求解接口

### D2.1 独立生成可行 incumbent

实现一个便宜、确定性、可重放的可行方案构造器。允许使用启发式充电目标来寻找**初始可行解**，但这些目标不得限制精确搜索的动作空间。

该构造器不能读取 REF 的最优结果，也不能把 FLAT 的最终最优解免费提供给 HIER。

正式比较中，FLAT 与 HIER 使用**同一个已验证初始解**；初始解生成时间、查询与内存计入系统成本。

构造失败只返回 `incumbent_search_failed`，不得断言原问题不可行。

### D2.2 从 incumbent 推导相关深度

使用已声明的正停车成本条件：

\[
H_{\max}
=
\left\lfloor
\frac{U_J}{h_{\min}+\lambda_{\mathrm{stop}}}
\right\rfloor.
\]

保留 H4 作为回归诊断接口，但正式 M5-D 结果不能依靠一个未声明的 H4 截断。

如果推导出的相关深度太大而无法完成，要报告真实的计算边界；不能把它重新压回 4 再报成功。

### D2.3 精确停止与中断恢复

保存 incumbent、OPEN 的有效下界、未处理域、表示版本和源码指纹。检查点恢复必须保持同一搜索域。

仅有主目标下界时，继续使用：

\[
L_J>U_J
\]

才能剪枝。等号节点必须保留，除非另有已证明的完整字典序证书。

---

## D3. 实现可部署的道路查询和 Region 下界

这是本轮最重要的算法开发任务。

### D3.1 道路查询接口

在保持不可变 selected-leg 语义的前提下，引入按需查询与缓存接口。缓存键至少绑定道路图、路由策略、起终点和数值契约。

要求：

- 相同物理 anchor 的查询可以复用；
- 不得对每个连续状态或 frontier piece 重跑全图最短路；
- 不能把选定 leg 当作新的普通图边重新路由，从而改变原先的 selected-fastest-leg 语义；
- 查询返回的时间、实际长度与 witness 必须能够追溯到同一条路；
- 预计算、加载、查询、缓存命中分别计时。

小域可以保留完整 leg table；正式大域不得把生成这张表的成本藏在计时之外。

### D3.2 无逐成员扫描的内部 Region 下界

新增可选的 `RegionBoundProvider`，与旧有限域实现并存。

目标是：正常搜索中，内部 Region 下界不枚举其全部 Site，不调用每个成员的精确 leg evaluator。

首先实现**点到 Region 的 directed ALT 摘要**和固定目的地方向摘要。对 landmark \(\ell\)，预计算 Region 的定向最小值、最大值，可构造：

\[
\underline d_T(v,R)
=
\max\left\{
0,\
\max_\ell\left[
\min_{s\in R}d_T(\ell,s)-d_T(\ell,v)
\right],\
\max_\ell\left[
d_T(v,\ell)-\max_{s\in R}d_T(s,\ell)
\right]
\right\}.
\]

证明并测试方向、不可达值和子集使用规则。不能直接对 \(\infty-\infty\) 做算术。

目的地方向使用同类摘要；已有 boundary tightening 只有在其前提对当前 Region/候选视图成立时才能接入。否则保留较弱但安全的 ALT，而不是强行复用 one-stop 公式。

这些是**本轮待实现并验证的设计要求**，不是声称当前代码已经具备。

### D3.3 下界的证明责任

每个下界提供：

1. 所松弛的原始约束；
2. 对全部被表示动作成立的推导；
3. 所需预计算与查询级成本；
4. 对空集、不可达和开放 cut 的处理；
5. 独立小域数值检查。

验证 admissibility 不要求对每个大域节点重做一次完整精确后续优化。可以检查一个已证明的安全松弛或解析证书，但必须明确证书证明的是**下界有效**，不是精确后续最优值。

### D3.4 防止把扫描转移到别处

计时模式不得为了日志或 coverage 检查，在每个内部节点重新物化全部成员列表。

正常执行、证据记录和离线检查分别核算。允许离线 checker 扫描，但不能用“下界没有扫描”掩盖另一个在线函数做了同样的扫描。

---

## D4. 设计真正有区分力、但工作量受控的开发集

### D4.1 先做数据可行性检查

不要因为 OD 地理距离长，就称它需要多次充电。每个实例应同时记录：

- 最优/最终方案的充电停靠数；
- 已证明的最少充电次数下界，或明确标为未知；
- 候选 Site 数；
- 实际探索深度；
- 是否带时间窗需求。

例如，在当前非负驱动能耗模型下，可使用：

\[
Q_{\mathrm{req}}^{LB}
=
\max\{0,E_{\mathrm{reserve}}+\kappa d_D(o,z)-E_0\}
\]

与单次最大补能量给出保守的充电次数下界。它可能很弱，但不能用未经证明的“看起来需要三次”替代证据。

若现有地理范围无法提供足够的真实多充电实例，先提交一个**最小必要数据扩展设计**。不得直接换成全国中国数据，也不得通过不合理缩小电池来把普通案例包装成长途实证。人工电池压力测试可以做，但必须独立标注。

### D4.2 分三级执行

| 层级 | 建议规模 | 目的 |
|---|---:|---|
| Pilot | 6 个基础查询，候选数 8/16/32 | 验证接口、真实多停靠和资源增长 |
| 主开发集 | 12 个 OD × 2 个 SOC × 2 个活动情景，共 48 个查询；主候选数 32/128 | 检验规模与时间窗的影响 |
| 完整候选检查 | 预先指定至少 6 个查询 | 识别候选截断造成的结论边界 |

候选数 16/64 或更大规模作为预先声明的补充阶梯，不无限扩张全因子实验。

至少争取让主开发集中的 12 个查询具备“需要两次或以上充电”的独立支持。达不到时记录数据门未通过，不得通过事后挑选或删掉简单案例凑数。

### D4.3 选样规则

所有 OD、SOC、活动窗口、候选选取、重复次数和排除规则，必须在正式比较结果出来前冻结。

嵌套候选集应满足：

\[
S_{16}\subseteq S_{32}\subseteq S_{64}\subseteq S_{128}.
\]

这些子集是**规模实验域**，不是自动覆盖全部优质方案的证明。完整域比较必须另报。

留出集以 OD/地理组为单位隔离，不能只把相同 OD 换个 SOC 就叫独立 holdout。

---

## D5. 比较方法与消融：既证明正确，也证明为什么有用

### D5.1 主比较

主比较只改变层次动作搜索，其他条件一致：

| 方法 | 用途 |
|---|---|
| FLAT-Exact | 相同 cut、相同 reduction、相同缓存与 incumbent 的平坦精确基线 |
| HIER-Deployable | 新的摘要式 Region 下界与层次动作搜索 |
| HIER-MemberScan | 当前逐成员下界版本，仅在可承受子集作诊断对照 |

不要让 HIER 使用更好的 seed、更热的缓存或额外预计算，而把 FLAT 留在较差条件。

### D5.2 代表性消融，而非全量组合爆炸

在预先选定的代表性子集上比较：

- reduction 开/关；
- exact adjacent-cut coalescing 开/关；
- 基础摘要下界与通过验证的 tightening；
- cold 与 warm 查询。

同一主比较必须使用一致的 coalescing 设置，才能把收益归因于 hierarchy，而不是表示压缩。

### D5.3 文献基线

增加一项有时间上限的相关工作与可比性审查，至少覆盖 CHArge、非线性充电 EVRP 的精确递推方法、带充电时间 completion bound 的 labeling 方法。

对每个候选基线写清：道路域、充电函数、时间窗、目标、是否允许同址活动并行、是否处理未达到最优值、是否能在相同输入上公平运行。

不能仅与自家 FLAT 比较后宣称“优于现有最先进算法”。若外部实现无法获得或问题域不一致，明确保留限制，避免花数周重写一个并不公平的竞争算法。

### D5.4 运输价值实验

除 solver 时间，还要回答：

> 联合安排停车、充电和活动，相比一个合理的先充电后安排活动的基线，究竟节省了什么？

报告 \(T_{\mathrm{clock}}\)、充电与活动重叠时间、停车数、时间窗满足、总充电量以及绕行。所有基线方案都须重放物理可行性。

不得把“同样到达时间下少充了电”误写成“更快到达”，也不得把模型内改进写成已经验证的用户满意度。

---

## D6. 正确性、核算和统计

### D6.1 正确性要求

必须保留历史两个关键反例的 v2 正确行为、开放 cut 经等待平台变为 attained 的构造，以及 \(Q\) 在达到的 \(J\)-最优面上仍可能未达到的情况。

新增实现至少完成：

- 小域独立 REF 对照；
- selected-leg 与停车事件重放；
- bound admissibility；
- action partition；
- reduction/coalescing 的域限制与 witness 保留；
- 初始解与深度证书；
- exact、未达到、不可行与资源中断状态的区别。

不同求解器可返回**不同的连续充电分配**，只要完整最优 key 一致且各自 witness 合法；除非先另行定义 canonical witness 顺序，否则不得要求充电向量字节一致。

### D6.2 成本分账

至少分别报告：

\[
T_{\mathrm{total}}
=
T_{\mathrm{query\ setup}}
+
T_{\mathrm{routing}}
+
T_{\mathrm{incumbent}}
+
T_{\mathrm{search}}
+
T_{\mathrm{witness}}.
\]

全局离线预处理、加载、离线独立验证另报。不能只报告 `search` 的加速而忽略总时延，也不能把离线百万级证书检查混入在线求解时延。

记录 Region 访问、成员访问、精确动作展开、PWA piece、OPEN、缓存和 RSS。不同类型操作先分别报告，不要随意相加制造一个“工作量削减率”。

零基线分母记为 `NA`，不强制写成 0% 或 100%。

### D6.3 统计

主结论同时给出全体案例的完成率和资源中断率，以及配对完成案例的耗时比。耗时比较按 OD 分组报告不确定性；不能把同一 OD 的重复计时当成独立样本。

所有 timeout、memory limit、初始解失败都保留在总体分母中。只对双方成功案例报加速时，必须同时显示该子集占比。

---

## D7. 资源上限与结束条件

### D7.1 默认资源预算

下列是本轮建议的执行上限，实际硬件不足时只能先降低并记录，不能突破机器安全余量：

| 阶段 | 单案例墙钟上限 | 单进程 RSS | 并发 |
|---|---:|---:|---:|
| Pilot | 120 秒 | 4 GiB | 1 |
| 正式开发评估 | 600 秒 | 8 GiB | 最多 2 |
| 整轮新增数值工作 | 累计 48 CPU 小时 | 聚合不超过 16 GiB，且保留主机余量 | 受监督 |

达到限制应终止完整进程组、保存结果状态与最后 checkpoint，不留后台 worker。

### D7.2 区分三类问题

**正确性或语义矛盾：**立即停止受影响阶段，不在同一轮发明新理论继续跑。

**普通实现缺陷：**在不改数学契约的前提下允许修复；保留失败记录并重跑受影响回归，不需要每次再创建一个新 milestone。

**性能不足：**正常记录，不视为理论错误。Pilot 后最多选择一次有明确复杂度依据的优化迭代；不能反复换参数、加缓存直到数据好看。

### D7.3 完成不等于必须获得正面性能结论

最终必须给出以下之一：

```text
M5D_COMPLETED_WITH_COMPUTATIONAL_BENEFIT
M5D_COMPLETED_WITHOUT_DEMONSTRATED_BENEFIT
M5D_LIMITED_BY_DATA_OR_SCALE
M5D_BLOCKED_BY_CORRECTNESS
```

可以把“主要工作集完成率不低于 90%、配对端到端几何平均加速至少 1.25 倍、置信区间下界大于 1”作为**本轮预注册的工程目标**，但它不是论文录用条件，也不能在看到结果后修改。

---

## D8. 交付物与交接点

本轮只维护少量稳定入口，避免再次产生几十份相互引用的恢复报告。

```text
docs/CURRENT_RESEARCH_STATUS.md
docs/MILESTONE_5D_DESIGN_AND_PROTOCOL.md
docs/MILESTONE_5D_REPORT.md
docs/PAPER_POSITIONING.md

results/milestone_5d/<run_id>/
    source_manifest.json
    environment_manifest.json
    dataset_manifest.json
    workload_manifest.json
    benchmark_results.jsonl
    verification_results.jsonl
    acceptance.json

paper/
    claims_evidence.md
    related_work.md
    outline.md
    figures/
```

必须交付：新接口与测试、现有模型域说明、全部结果及失败行、可复现命令、主要瓶颈解释、与文献的可比性矩阵，以及不含虚构结果的论文提纲。

创建待审查 PR，不自动合并。更新 README 当前入口，但不覆盖历史验收文件。

**结束时停止。**提交 M6-H 的建议协议和封存方法，等待确认后才运行最终 holdout。

---

# 三、M5-D 之后，还剩哪些必要步骤？

按成功终点 A，后续不是再开一串模糊 milestone，而是三个明确出口。

## 1. M5-D：计算收益与适用范围

回答：

> 在真正多次充电和更大候选空间下，层次方法是否保持正确，而且减少实际总成本？

这一阶段允许得到负面结果。若只能在很小的域内完成，就如实报告适用边界，不能靠增加文档把“可证明有限”写成“可部署高效”。

## 2. M6-H：冻结后独立验证

冻结算法、数据处理、候选规则、阈值和统计方法，再用未用于开发决策的 OD/区域组验证。

独立 holdout 不意味着整个大域都有一个可运行的完整 REF。可以分成小域精确对照与大域完整性证书、物理 witness 和性能测试；每类证据说明范围，不能互相冒充。

## 3. Paper closure：把工程结果变成可审查的科研结论

论文需要完成最近相关工作的逐项比较、定理假设与证明整理、运输价值分析、限制讨论和最小可复现材料。当前仓库的审计材料是很好的证据来源，但不应直接成为论文叙事结构。

作为**排期预算而非工期承诺**，我建议为 M5-D 留 15–25 个有效工作日，holdout 与最终整理再留 10–20 个工作日，论文定位与初稿并行推进。新地理数据建设或新的数学矛盾会额外增加时间；不应继续沿用缺乏可审计分母的“已经完成 80%–85%”估计。