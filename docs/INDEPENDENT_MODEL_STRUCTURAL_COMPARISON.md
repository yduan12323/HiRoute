# 独立模型的共同输入契约与结构比较

工程范围说明，非论文稿。本次只读取现有任务书、模型、证明和结果；没有新求解或
基准。全文核对的任务书为`HIROUTE_REAL_SCALE_DECISION_AND_PLAN.md`（370行）。
旧的“先完成全源道路证明才可比较”路线是后来选取的更强校验，不应被误写成原始
验收条件。本文件说明合规实现选择，不更改过去失败、物理模型或优化目标。

## 1. 原任务书的明确许可

§5.3原句：

> 接受真实道路 provider 或冻结 directed leg provider，禁止将 selected legs 重新作为普通路网绕路优化。

> 对 N^2 表预计算，若使用必须计入成本；不把全表免费放在实验之前。

> 路由正确性抽查使用独立小图/路径重放；不要求在整个真实图上调用枚举 simple paths 的 REF。

§8.1原句：

> 针对相同域选择至少一个可比的已有 exact routing/labeling 方法或可独立建立的优化模型；明确其不支持的 schedule、目标或充电行为。

> 只在共同支持域进行公平比较，不能通过丢弃约束让某个方法“更快”，也不能故意给基线弱实现。

> 若无法取得可运行实现，用可审查的独立模型和结构性比较说明限制；不得宣称全面超过 SOTA。

**结论：共同、精确、声明完整并计费的selected-leg输入，配以独立编码的优化模型，
已在任务书允许范围内。选择该实现不需要新增研究范围批准。** 公共输入不等于调用
Core/REF当优化oracle。§6.1的Strong/Scale共享内核要求，也不应被误读为独立模型
必须复用生产优化器。道路契约需按§5.3检验和披露；不能把schema/hash通过说成原始
路网最短路证明，但任务书没有强制65个源各自全图数学证书。

本次仍不运行真实比较，因为当前委派禁止新数值；这是执行与预算限制，不是共享
输入方案未获模型许可。已经承诺的更强道路校验明确记录为未完成，不静默改名为成功。

## 2. 三层正确性及当前边界

| 层次 | 要保证什么 | 现有证据／缺口 |
|---|---|---|
| 声明输入的身份与完整性 | literal Site/action/Pi、全部合法有向pair、原点/终点、alias-zero；不能用缺记录充当不可达 | `ExactLegTable`及grounded lookup有所有权、覆盖和corruption测试；完整真实CSR已逐raw边核验。真实4225项leg表尚未完成 |
| 道路选择契约 | 最小精确时间，再完整node tuple、string edge-ID tuple；长度取该路径，方向性与实际路径重放正确 | 生产provider、小图独立selector及重放有已有验证。完整原始图的独立source数学证书为0；两次导出UNKNOWN。公共输入比较须显式承认共同路由假设 |
| 给定输入上的优化正确性 | 独立物理约束、full K、严格支持、attainment与完整相关深度；结果witness重放 | 已有独立有理数/SMT实现与tiny解析证据；没有真实共同域优化行，不能宣称真实端到端独立证明或速度领先 |

在冻结leg表上比较证明的是“给定该精确声明表及物理模型”的优化结论。它不同时证明
所有pair来自原始图的全局canonical shortest path。这个条件化边界必须写出；不能把
“独立优化模型”偷换成“完全独立的端到端道路系统”，反过来也不应无限加强输入
证明要求而阻断任务书已经允许的比较。

## 3. 已实现模型的结构对照

| 事项 | Strong/Scale生产路径 | 独立模型路径 | 共同语义／限制 |
|---|---|---|---|
| 搜索表示 | 准确post-stop PWA family、增量C/S/CS及terminal尝试；两方法仅查询组织不同 | 独立slot/action/segment/max selectors及两份连续变量，不调用Core/REF求解 | 同一合法历史集合、相同物理参数；不是把Core换名字 |
| 路由与能耗 | exact selected leg的time与该路径实际length；下界另用合法distance relaxation | `ExactLegTable`常量通过grounded lookup取值，消耗rho*实际length | 不把leg表重新路由，不用shortest-length代替selected-fastest长度，不假设该长度满足三角不等式 |
| C、S、CS | 现行exact time-cut算子与witness | 独立线性/分支方程和Fraction replay | C结束为arrival+h+delta；S为max(a+D,arrival+h+D)；CS再纳入arrival+h+delta，活动latest-start允许等号 |
| 充电曲线 | 声明的连续PWA时间曲线 | 所有给定piece的入/出段selectors，Phi(Eout)-Phi(Ein) | 不能以平均功率替代；当前独立schema的共同曲线/参数支持边界须逐输入核对，不声称任意异构站点模型 |
| 正充电与闭包 | physical family保留严格q>0及开放端点 | 同一离散fiber内共享selectors，闭包点与严格支持点分离 | 先证明fiber有严格点才可用其闭包；全局q>=0替换会引入严格空分支的伪解 |
| 目标与attainment | J、Q、H、Pi及最优面摘要；open infimum不能作incumbent | 先求J并检查主面严格可达，再在主面求Q/联合attainment，最后H/Pi | exact rational bounds及SAT/UNSAT审计，不使用浮点gap或printed model当最优证明 |
| 终点、alias、重复访问 | prefix为空与terminal不可行分开；合法重复Site/history不粗合并 | inactive suffix、独立terminal drive、literal动作与物理anchor分开 | alias-zero仍可有正充电和停靠成本；活动只消费一次；terminal失败不阻止之前可充电的prefix |
| 相关深度与上界 | 明确可行seed用于U，h_min+lambda给安全相关深度 | 独立重放实际可行witness后推floor(U/(h+lambda))，或合法更紧式 | 不是任意H=6；过大则UNKNOWN/unsupported，不截断后冒称全域精确。没有seed不证明不可行 |
| 输出与资源 | 物理重放及明确attained/unattained/UNKNOWN | 单独具体Fraction replay，严格优于候选的UNSAT等检查，deadline后再检查终态 | 共享资源口径；超时、无解witness与证明不可行分开 |

上述模型针对已声明的单活动、非负消费/停车罚时、正overhead和给定连续正斜率充电
曲线；不声称覆盖任意EVRP、动态交通、站点实时可用性或额外活动。生产PWA表示与
独立线性selector形式不同，但两者不是完全无共同软件假设的实现：独立模型使用Z3，
早期模型/replay及tiny输入有共享工具。独立性具体限定为相对生产优化内核的公式与求解路径。

## 4. 既有结果能支持什么

- [最初独立模型](INDEPENDENT_COMPARATOR_GATE.md)：12个冻结解析例，含attained、
  primary/secondary unattained、infeasible；受2Site/2stop等明确tiny边界约束。
- [compact设计](COMPACT_COMPARATOR_GATE.md)：13例及196个gate检查/模式，selector
  取代plan/branch枚举，证明严格支持必须同时约束正确目标面；旧prototype guards未被偷偷删除。
- [完整物理适配](EXACT_PHYSICAL_ADAPTER.md)：8类、116个gate SMT检查，6个attained、
  两类unattained；支持所有给定充电piece、alias和重复访问，有独立重放及完整相关深度论证。

这些cohort重叠，不能相加当成独立真实样本，也不能把full-width construction probe
当作真实求解。它们已足以交付可审查模型及结构性限制说明，但没有真实规模优化
性能或原始路网完全独立最优证明。已有文献核对见
[范围审计](RESEARCH_ROUTE_REASSESSMENT.md#targeted-primary-source-audit)：
它尚未建立可运行的同模型CHArge等适配，也不是exhaustive novelty/SOTA clearance。
不把相关方法的不同问题设定、摘要或速度转移为本模型的比较结果。

## 5. 推荐的合规窄比较设计（未执行）

1. 固定一个已有合法声明域，以真实exact provider生成或读取**完整**共同有向leg表。
   当前N64固定域需65x65=4225项，含64个alias-zero项、空prefix的OD项及所有terminal项。
   单向不可达必须来自provider结论，缺项仍是缺项。Site/动作/Pi不与anchor合并。
2. 明确时间、selected实际长度、canonical tie、参数与合法动作一致；保留已有独立小图
   检查及实际路径/物理重放。表的准备、路由、冷启动、驻留、缓存和序列化均计费。
   **完整原始图source证书不是前置条件**；未取得时只作共同输入下的独立优化比较。
3. 由独立具体重放确认实际可行U及相关H，再输入独立物理模型。历史joint最终witness
   可以作为明确披露、已计生成成本且重新重放的可行数据，不能冒充免费REF oracle或
   新seed；不得把待证的最优值或完整key当作答案约束，旧结果仅作终态后的比较控制。
   若初始信息与历史Strong/Scale不相同，则只比较状态/精确key/重放，不宣称
   当代公平速度。任何公平计时设计另需同信息/同预算，不能从现有历史时间直接推出。
4. 仅在共同支持语义上比较：q>0、CS max、曲线全部piece、初始等待、终点reserve、
   重复访问、full K及attainment不可丢弃。缺输入/不支持/超时完整报告；不把有限H或
   owned-table schema通过当作全模型精确完成。每个attained结果具体重放。

这是已获任务书许可的默认实现方向，不需要再问一次“是否允许共享输入”。当前没有
新增数值额度/实跑许可，真实表准备、独立U重放和真实模型运行仍是尚未执行的工作，
本文没有代替它们。两个旧源导出UNKNOWN、所有原始ledger与负面证据保持原样。

## 6. 生产速度仍需另一项结构性工作

即使共同输入比较可用，也不修复N64已有95%/60s和median10s失败。现有硬schedule
数据指向exact continuation工作，但计时嵌套且未分离各primitive；不能凭总数指定一个
必定有效的新剪枝。可信候选应从准确family的能量/时间/活动相关性，或C/CS/PWA表示
和transition成本出发，证明保留严格支持、相等面、full K和全部相关深度，并将新增
信息公平提供给Strong与Scale。仅重包Region、增加缓存或改源证书格式，不是该问题
已验证的结构性解法。这里仅标明应解决的问题，没有实现第二架构或安排新的tiny/real gate。
