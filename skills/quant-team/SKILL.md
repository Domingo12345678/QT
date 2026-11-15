---
name: quant-team
description: 运行两层量化研究团队，协调分配、生成、检查组并查询系统状态
whenToUse: 用户要求量化研究、回测、策略检查、查看团队状态或提交系统指令时
---

把用户请求视为更新层输入，始终由分配组协调生成组和检查组，禁止生成组与检查组直接对接。

按请求选择最小操作：

1. 查询状态：运行 `python "${KIMI_SKILL_DIR}/../../quant_system.py" status`，汇总各组状态、最近任务和最近指令。
2. 验证框架：运行 `python "${KIMI_SKILL_DIR}/../../quant_system.py" run "$ARGUMENTS"`。未提供价格时结果使用合成示例数据，必须明确标注，不得解释为真实策略表现。
3. 记录更新指令：运行 `python "${KIMI_SKILL_DIR}/../../quant_system.py" command "$ARGUMENTS"`，确认已接受；涉及实际修改时先说明范围，再实施。
4. 真正的研究任务：把完整任务交给 `quant-allocator`，由其依次委托 `quant-generator` 和 `quant-checker`。不要直接调用后两个角色。

状态保存在当前项目的 `.qt/state.json`。本框架不连接实盘、不自动下单；检查通过不等于投资建议。
