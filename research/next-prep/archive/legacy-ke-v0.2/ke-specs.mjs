export const slotExpressions = new Map();

function slot(candidateId, turnIndex, speaker, ...expressions) {
  slotExpressions.set(`${candidateId}|${turnIndex}|${speaker}`, expressions);
}

// Work management and vacation disclosure.
slot("WILDCHAT-MGMT-CAND-001", 1, "user",
  "employer_of(Person_用户)=Org_律师事务所",
  "needs_more_work(Person_用户)=Boolean_true",
  "planning_window_of(Event_出国休假)=Duration(\"P2M\")",
  "duration_of(Event_出国休假)=Duration(\"P7D\")",
  "asks_about(Person_用户,Topic_休假披露时机)=Boolean_true",
  "concerned_about(Person_用户,Topic_休假影响工作分派)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-001", 1, "agent",
  "recommends(Agent_助手,Action_尽早透明沟通休假)=Boolean_true",
  "recommends(Agent_助手,Action_说明交付安排)=Boolean_true",
  "requires(Action_出国休假,Req_交接安排)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-001", 2, "user",
  "status_of(Topic_事务所工作量)=Status(\"low\")",
  "asks_about(Person_用户,Topic_获取工作分派方式)=Boolean_true",
  "considers(Person_用户,Option_联系事务所合伙人)=Boolean_true",
  "considers(Person_用户,Option_联系前律所转介)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-001", 2, "agent",
  "recommends(Agent_助手,Action_主动联系分派工作的合伙人)=Boolean_true",
  "recommends(Agent_助手,Action_跨业务组提供支持)=Boolean_true",
  "recommends(Agent_助手,Action_参加所内活动)=Boolean_true",
  "recommends(Agent_助手,Action_合规开展业务拓展)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-001", 3, "user",
  "chooses(Person_用户,Option_联系合伙人与业务拓展)=Boolean_true",
  "date_range_of(Event_出国休假)=DateRange(RelativeDate(\"December-15\"),RelativeDate(\"December-26\"))",
  "asks_about(Person_用户,Topic_是否现在披露休假)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-001", 3, "agent",
  "recommends(Agent_助手,Action_现在说明休假日期)=Boolean_true",
  "recommends(Agent_助手,Action_强调休假前后可工作)=Boolean_true",
  "recommends(Agent_助手,Action_提前完成任务与交接)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-001", 4, "user",
  "plans(Person_用户,Plan_发送可接工作邮件)=Boolean_true",
  "asks_about(Person_用户,Topic_客户X下一轮融资时间)=Boolean_true",
  "date_range_of(Event_出国休假)=DateRange(RelativeDate(\"December-15\"),RelativeDate(\"December-26\"))");
slot("WILDCHAT-MGMT-CAND-001", 4, "agent",
  "recommends(Agent_助手,Action_邮件先表达可承担项目)=Boolean_true",
  "recommends(Agent_助手,Action_邮件询问客户X融资时间)=Boolean_true",
  "recommends(Agent_助手,Action_邮件说明休假与交接)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-001", 5, "user",
  "role_of(Person_用户)=Role(\"senior lawyer\")",
  "asks_about(Person_用户,Topic_资深律师邮件语气)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-001", 5, "agent",
  "recommends(Agent_助手,Action_使用简洁自信的邮件语气)=Boolean_true",
  "recommends(Agent_助手,Action_说明当前可接新工作)=Boolean_true",
  "recommends(Agent_助手,Action_说明休假交接安排)=Boolean_true");

// Android debugging and learning.
slot("WILDCHAT-LEARN-CAND-001", 1, "user",
  "required_compile_sdk_of(Dep_androidx_activity_1_8_0)=Integer(34)",
  "required_compile_sdk_of(Dep_activity_ktx_1_8_0)=Integer(34)",
  "required_compile_sdk_of(Dep_activity_compose_1_8_0)=Integer(34)",
  "value_of(Param_compileSdk)=Integer(33)",
  "asks_about(Person_用户,Topic_修复compileSdk不兼容)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-001", 1, "agent",
  "recommends(Agent_助手,Action_将compileSdk更新到34)=Boolean_true",
  "path_of(Doc_app_build_gradle)=Path(\"app/build.gradle\")",
  "target_value_of(Param_compileSdk)=Integer(34)");
slot("WILDCHAT-LEARN-CAND-001", 2, "user",
  "asks_about(Person_用户,Topic_具体修改compileSdk步骤)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-001", 2, "agent",
  "target_value_of(Param_compileSdk)=Integer(34)",
  "recommends(Agent_助手,Action_同步Gradle并重新构建)=Boolean_true",
  "path_of(Doc_app_build_gradle)=Path(\"app/build.gradle\")");
slot("WILDCHAT-LEARN-CAND-001", 3, "user",
  "status_of(App_Android应用)=Status(\"crashes_on_launch\")",
  "asks_about(Person_用户,Topic_启动崩溃排查)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-001", 3, "agent",
  "uses(Task_运行时调试,Tool_Logcat)=Boolean_true",
  "recommends(Agent_助手,Action_检查依赖版本)=Boolean_true",
  "recommends(Agent_助手,Action_Clean_Rebuild)=Boolean_true",
  "recommends(Agent_助手,Action_核对Manifest配置)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-001", 4, "user",
  "error_of(App_Android应用)=Issue_AppCompat主题错误",
  "text_of(Issue_AppCompat主题错误)=Text(\"You need to use a Theme.AppCompat theme or descendant with this activity\")");
slot("WILDCHAT-LEARN-CAND-001", 4, "agent",
  "requires(Artifact_MainActivity,Req_Theme_AppCompat)=Boolean_true",
  "recommends(Agent_助手,Action_检查Manifest主题属性)=Boolean_true",
  "recommends(Agent_助手,Action_确认styles定义AppCompat主题)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-001", 5, "user",
  "asks_about(Person_用户,Topic_AndroidManifest位置)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-001", 5, "agent",
  "path_of(Doc_AndroidManifest)=Path(\"app/src/main/AndroidManifest.xml\")");
slot("WILDCHAT-LEARN-CAND-001", 6, "user",
  "asks_about(Person_用户,Topic_styles与Manifest修改顺序)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-001", 6, "agent",
  "precedes(Action_确认styles中AppCompat主题,Action_在Manifest引用主题)=Boolean_true",
  "requires(Artifact_MainActivity,Req_Theme_AppCompat)=Boolean_true",
  "recommends(Agent_助手,Action_失败后重新查看Logcat)=Boolean_true");

// Content operations.
slot("WILDCHAT-MGMT-CAND-002", 1, "user",
  "requests(Person_用户,Plan_三十天内容运营)=Boolean_true",
  "duration_of(Plan_三十天内容运营)=Duration(\"P30D\")",
  "channel_of(Plan_三十天内容运营)=Platform_Telegram",
  "theme_of(Plan_三十天内容运营)=Theme_独占价值内容");
slot("WILDCHAT-MGMT-CAND-002", 1, "agent",
  "includes_step(Plan_三十天内容运营,Action_发布频道介绍)=Boolean_true",
  "includes_step(Plan_三十天内容运营,Action_发布深度文章)=Boolean_true",
  "includes_step(Plan_三十天内容运营,Action_举办专家直播)=Boolean_true",
  "includes_step(Plan_三十天内容运营,Action_发布互动问答)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-002", 2, "user",
  "revises(Plan_Telegram内容计划,Plan_Instagram内容计划)=Boolean_true",
  "channel_of(Plan_Instagram内容计划)=Platform_Instagram",
  "requires(Plan_Instagram内容计划,Req_博客_Reels_Stories)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-002", 2, "agent",
  "uses(Plan_Instagram内容计划,Method_轮播摘要)=Boolean_true",
  "uses(Plan_Instagram内容计划,Method_Reels短教程)=Boolean_true",
  "uses(Plan_Instagram内容计划,Method_Stories故事叙述)=Boolean_true",
  "uses(Plan_Instagram内容计划,Method_Instagram_Live问答)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-002", 3, "user",
  "requests(Person_用户,Plan_连续Reels故事系列)=Boolean_true",
  "theme_of(Plan_连续Reels故事系列)=Theme_转变故事");
slot("WILDCHAT-MGMT-CAND-002", 3, "agent",
  "includes_step(Plan_连续Reels故事系列,Action_第一集迈出第一步)=Boolean_true",
  "includes_step(Plan_连续Reels故事系列,Action_第二集接受不完美)=Boolean_true",
  "includes_step(Plan_连续Reels故事系列,Action_第三集自我照顾)=Boolean_true",
  "requires(Plan_连续Reels故事系列,Req_冲突经历反思问题结构)=Boolean_true");

// Praat and PSOLA learning.
slot("WILDCHAT-LEARN-CAND-002", 1, "user",
  "requests(Person_用户,Plan_居字声调连续体)=Boolean_true",
  "step_count_of(Plan_居字声调连续体)=Integer(9)",
  "uses(Plan_居字声调连续体,Tool_Praat)=Boolean_true",
  "uses(Plan_居字声调连续体,Method_PSOLA)=Boolean_true",
  "source_tone_of(Stimulus_普通话居)=Tone(\"2\")",
  "target_tone_of(Stimulus_普通话居)=Tone(\"3\")");
slot("WILDCHAT-LEARN-CAND-002", 1, "agent",
  "includes_step(Plan_居字声调连续体,Action_载入二声录音)=Boolean_true",
  "includes_step(Plan_居字声调连续体,Action_提取F0曲线)=Boolean_true",
  "includes_step(Plan_居字声调连续体,Action_生成九组目标值)=Boolean_true",
  "includes_step(Plan_居字声调连续体,Action_PSOLA替换音高)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-002", 2, "user",
  "error_of(Task_F0提取)=Issue_无法导出文本文件",
  "asks_about(Person_用户,Topic_F0文本导出步骤)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-002", 2, "agent",
  "output_of(Task_F0提取)=Doc_F0文本文件",
  "path_of(Doc_F0文本文件)=Path(\"F0.txt\")",
  "requires(Task_F0提取,Req_合适的音高范围与算法)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-002", 3, "user",
  "changes(Plan_居字声调连续体,Param_F0转折点)=Boolean_true",
  "changes(Plan_居字声调连续体,Param_F0_offset)=Boolean_true",
  "equal_spacing_of(Plan_居字声调连续体)=Boolean_true",
  "uses(Plan_居字声调连续体,Method_PSOLA)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-002", 3, "agent",
  "includes_step(Plan_居字声调连续体,Action_录音转Pitch)=Boolean_true",
  "includes_step(Plan_居字声调连续体,Action_Pitch转Manipulation)=Boolean_true",
  "includes_step(Plan_居字声调连续体,Action_替换目标音高)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-002", 4, "user",
  "available_in(Tool_Scale_pitch,Tool_Praat当前版本)=Boolean_false",
  "asks_about(Person_用户,Topic_Scale_pitch替代步骤)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-002", 4, "agent",
  "recommends(Agent_助手,Action_使用Replace_pitch)=Boolean_true",
  "requires(Action_使用Replace_pitch,Req_设置起始终止平均音高)=Boolean_true",
  "recommends(Agent_助手,Action_检查转折点和offset并试听)=Boolean_true");

// Performance management.
slot("WILDCHAT-MGMT-CAND-003", 1, "user",
  "requests(Person_用户,Plan_高级项目经理绩效目标)=Boolean_true",
  "goal_count_of(Plan_高级项目经理绩效目标)=Integer(10)");
slot("WILDCHAT-MGMT-CAND-003", 1, "agent",
  "includes_goal(Plan_高级项目经理绩效目标,Goal_项目执行效率)=Boolean_true",
  "includes_goal(Plan_高级项目经理绩效目标,Goal_居民满意度)=Boolean_true",
  "includes_goal(Plan_高级项目经理绩效目标,Goal_跨部门协作)=Boolean_true",
  "includes_goal(Plan_高级项目经理绩效目标,Goal_员工培训)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-003", 2, "user",
  "requests(Person_用户,Action_增加绩效目标)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-003", 2, "agent",
  "includes_goal(Plan_高级项目经理绩效目标,Goal_资本改造按预算进度完成)=Boolean_true",
  "includes_goal(Plan_高级项目经理绩效目标,Goal_降低空置率)=Boolean_true",
  "includes_goal(Plan_高级项目经理绩效目标,Goal_改进维修响应)=Boolean_true",
  "includes_goal(Plan_高级项目经理绩效目标,Goal_灾害准备)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-003", 3, "user",
  "revises(Plan_高级项目经理绩效目标,Plan_SMART绩效目标)=Boolean_true");
slot("WILDCHAT-MGMT-CAND-003", 3, "agent",
  "target_value_of(Goal_提高入住率)=Percent(10)",
  "deadline_of(Goal_提高入住率)=RelativeDate(\"next fiscal year\")",
  "target_value_of(Goal_缩短维修响应时间)=Percent(20)",
  "duration_of(Plan_员工培训)=Duration(\"P6M\")");

// Python, formulas, and Pandas.
slot("WILDCHAT-LEARN-CAND-003", 1, "user",
  "asks_about(Person_用户,Topic_make_hyperlink函数语义)=Boolean_true",
  "template_of(Formula_make_hyperlink)=Text(\"./{}\")");
slot("WILDCHAT-LEARN-CAND-003", 1, "agent",
  "input_type_of(Formula_make_hyperlink)=Type_Text",
  "output_type_of(Formula_make_hyperlink)=Type_Hyperlink公式",
  "template_of(Formula_make_hyperlink)=Text(\"./{}\")");
slot("WILDCHAT-LEARN-CAND-003", 2, "user",
  "requests(Person_用户,Action_演示make_hyperlink)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-003", 2, "agent",
  "argument_of(Action_make_hyperlink示例)=Text(\"example\")",
  "output_of(Action_make_hyperlink示例)=Formula_HYPERLINK_example");
slot("WILDCHAT-LEARN-CAND-003", 3, "user",
  "asks_about(Person_用户,Topic_Pandas_apply参数)=Boolean_true",
  "requests(Person_用户,Action_演示Pandas_apply)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-003", 3, "agent",
  "applies_formula(DataFrame_df,Formula_make_hyperlink)=Boolean_true",
  "input_column_of(DataFrame_df)=Column_Value",
  "output_column_of(DataFrame_df)=Column_Hyperlink");

// Learning science claims.
slot("WILDCHAT-LEARN-CAND-004", 1, "user",
  "asks_about(Person_用户,Claim_学习风格显著影响学习)=Boolean_true",
  "requests(Person_用户,Action_给出证据结论与实践建议)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-004", 1, "agent",
  "supported_by(Claim_固定听视动学习风格,Evidence_研究证据)=Boolean_false",
  "recommends(Agent_助手,Strategy_多模态主动差异化教学)=Boolean_true",
  "recommends(Agent_助手,Action_根据实际表现调整方法)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-004", 2, "user",
  "asks_about(Person_用户,Claim_学习困难学生能力固定)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-004", 2, "agent",
  "supported_by(Claim_学习困难学生能力固定,Evidence_研究证据)=Boolean_false",
  "supports(Strategy_早期识别个别化计划差异化教学,Goal_学生能力发展)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-004", 3, "user",
  "asks_about(Person_用户,Claim_记忆是成功学习的唯一关键)=Boolean_true");
slot("WILDCHAT-LEARN-CAND-004", 3, "agent",
  "supported_by(Claim_记忆是成功学习的唯一关键,Evidence_研究证据)=Boolean_false",
  "supports(Method_深层理解,Goal_长期学习)=Boolean_true",
  "supports(Method_检索练习,Goal_长期学习)=Boolean_true",
  "supports(Method_刻意练习,Goal_长期学习)=Boolean_true");

// Flight planning.
slot("TASKMASTER2-CAND-001", 1, "user",
  "requests(Person_用户,Action_预订往返航班)=Boolean_true",
  "origin_of(Flight_候选往返航班)=Location(\"New York City\")",
  "destination_of(Flight_候选往返航班)=Location(\"Amsterdam\")",
  "trip_type_of(Flight_候选往返航班)=Type(\"round_trip\")");
slot("TASKMASTER2-CAND-001", 1, "agent",
  "asks_about(Agent_助手,Topic_航班其他偏好)=Boolean_true");
slot("TASKMASTER2-CAND-001", 2, "user",
  "departure_date_of(Flight_候选往返航班)=RelativeDate(\"today\")",
  "return_date_of(Flight_候选往返航班)=DayOfMonth(19)",
  "prefers(Person_用户,Option_两程尽可能早)=Boolean_true");
slot("TASKMASTER2-CAND-001", 2, "agent",
  "accepts(Agent_助手,Req_日期与最早时间偏好)=Boolean_true");
slot("TASKMASTER2-CAND-001", 3, "user",
  "prefers(Person_用户,Option_最便宜航班)=Boolean_true");
slot("TASKMASTER2-CAND-001", 3, "agent",
  "price_of(Flight_最便宜方案)=Money(1287,Currency(\"USD\"))",
  "stop_count_of(Flight_最便宜方案)=Integer(1)",
  "departure_time_of(Flight_最便宜方案)=Time(\"00:30\")",
  "arrival_time_of(Flight_最便宜方案)=Time(\"11:55 next day\")",
  "offers(Agent_助手,Flight_最便宜方案)=Boolean_true");
slot("TASKMASTER2-CAND-001", 4, "user",
  "asks_about(Person_用户,Topic_直飞航班)=Boolean_true");
slot("TASKMASTER2-CAND-001", 4, "agent",
  "is_nonstop(Flight_直飞方案)=Boolean_true",
  "price_of(Flight_直飞方案)=Money(2677,Currency(\"USD\"))",
  "departure_time_of(Flight_直飞方案)=Time(\"18:00\")",
  "arrival_time_of(Flight_直飞方案)=Time(\"07:35 next day\")",
  "offers(Agent_助手,Flight_直飞方案)=Boolean_true");
slot("TASKMASTER2-CAND-001", 5, "user",
  "chooses(Person_用户,Flight_最便宜方案)=Boolean_true");
slot("TASKMASTER2-CAND-001", 5, "agent",
  "output_of(Action_发送航班信息)=Message_航班信息邮件",
  "delivery_channel_of(Message_航班信息邮件)=Email_用户邮箱");

// Tau-bench retail actions and tool results.
slot("TAU-BENCH-CAND-001", 1, "user",
  "requests(Person_用户,Action_退回平板)=Boolean_true",
  "requests(Person_用户,Action_取消充电器)=Boolean_true",
  "compatible_with(Product_充电器,Product_平板)=Boolean_true");
slot("TAU-BENCH-CAND-001", 1, "agent",
  "order_of(Product_平板)=Order_W2692684",
  "order_of(Product_充电器)=Order_W9373487",
  "refund_method_of(Action_退回平板)=Payment_礼品卡_7711863",
  "requires(Action_退回平板与取消充电器,Req_用户确认)=Boolean_true");
slot("TAU-BENCH-CAND-001", 2, "user",
  "confirms(Person_用户,Action_退回平板)=Boolean_true",
  "confirms(Person_用户,Action_取消充电器)=Boolean_true");
slot("TAU-BENCH-CAND-001", 2, "agent",
  "return_delivered_order_items(Order_W2692684,Product_平板,Payment_礼品卡_7711863)=ActionResult(\"return_requested\")",
  "cancel_pending_order(Order_W9373487,Reason(\"no longer needed\"))=ActionResult(\"cancelled\")",
  "refund_amount_of(Action_退回平板)=Money(951.21,Currency(\"USD\"))",
  "refund_amount_of(Action_取消充电器)=Money(109.27,Currency(\"USD\"))");
slot("TAU-BENCH-CAND-001", 3, "user",
  "requests(Person_用户,Action_退回运动鞋)=Boolean_true");
slot("TAU-BENCH-CAND-001", 3, "agent",
  "asks_about(Agent_助手,Topic_运动鞋订单号或最近订单)=Boolean_true");
slot("TAU-BENCH-CAND-001", 4, "user",
  "knows(Person_用户,Topic_运动鞋订单号)=Boolean_false",
  "item_in_recent_order(Product_运动鞋)=Boolean_true");
slot("TAU-BENCH-CAND-001", 4, "agent",
  "get_order_details(Order_W7449508)=ActionResult(\"found\")",
  "order_of(Product_运动鞋)=Order_W7449508",
  "status_of(Order_W7449508)=Status(\"delivered\")",
  "attribute_of(Product_运动鞋,Text(\"size\"))=Text(\"6\")",
  "attribute_of(Product_运动鞋,Text(\"color\"))=Text(\"black\")",
  "attribute_of(Product_运动鞋,Text(\"material\"))=Text(\"synthetic\")");
slot("TAU-BENCH-CAND-001", 5, "user",
  "confirms(Person_用户,Action_退回运动鞋)=Boolean_true",
  "refund_method_of(Action_退回运动鞋)=Payment_礼品卡_7711863");
slot("TAU-BENCH-CAND-001", 5, "agent",
  "return_delivered_order_items(Order_W7449508,Product_运动鞋,Payment_礼品卡_7711863)=ActionResult(\"return_requested\")",
  "refund_amount_of(Action_退回运动鞋)=Money(186.45,Currency(\"USD\"))");

// BEAM estate planning.
slot("BEAM-CAND-004", 1, "user",
  "executor_of(Person_Douglas,Will_用户遗嘱)=Boolean_true",
  "date_of(Event_Douglas接受执行人)=Date(\"2024-04-15\")",
  "location_of(Event_Douglas接受执行人)=Location(\"Coral Bay Café\")",
  "date_of(Meeting_家庭会议_0325)=Date(\"2024-03-25\")",
  "location_of(Meeting_家庭会议_0325)=Location(\"用户家\")",
  "participant_of(Person_Kimberly,Meeting_家庭会议_0325)=Boolean_true",
  "participant_of(Person_Bradley,Meeting_家庭会议_0325)=Boolean_true",
  "concerned_about(Person_用户,Topic_家人对执行人选择的看法)=Boolean_true");
slot("BEAM-CAND-004", 1, "agent",
  "recommends(Agent_助手,Action_向家人说明选择Douglas的原因)=Boolean_true",
  "recommends(Agent_助手,Action_讨论共同遗嘱执行人)=Boolean_true",
  "recommends(Agent_助手,Action_向Stephanie征求法律意见)=Boolean_true");
slot("BEAM-CAND-004", 2, "user",
  "plans(Person_用户,Plan_再次家庭会议)=Boolean_true",
  "goal_of(Plan_再次家庭会议)=Goal_面对面处理家人顾虑",
  "goal_of(Plan_再次家庭会议)=Goal_家庭团聚");
slot("BEAM-CAND-004", 2, "agent",
  "recommends(Agent_助手,Action_选择方便的会议时间地点)=Boolean_true",
  "recommends(Agent_助手,Action_准备家庭会议议程)=Boolean_true",
  "includes_step(Plan_再次家庭会议,Action_讨论执行人职责)=Boolean_true",
  "includes_step(Plan_再次家庭会议,Action_讨论共同执行人)=Boolean_true");
slot("BEAM-CAND-004", 3, "user",
  "requests(Person_用户,Action_起草家庭会议邀请)=Boolean_true",
  "requests(Person_用户,Action_起草家庭会议议程)=Boolean_true");
slot("BEAM-CAND-004", 3, "agent",
  "output_of(Action_起草家庭会议邀请)=Doc_家庭会议邀请",
  "output_of(Action_起草家庭会议议程)=Doc_家庭会议议程",
  "includes_step(Plan_家庭会议议程,Action_听取Kimberly和Bradley顾虑)=Boolean_true",
  "includes_step(Plan_家庭会议议程,Action_确认决定和后续步骤)=Boolean_true");
slot("BEAM-CAND-004", 4, "user",
  "deadline_of(Will_用户遗嘱)=Date(\"2024-05-15\")",
  "anchor_date_of(Turn_BEAM_004_4)=Date(\"2024-05-02\")",
  "executor_of(Person_Douglas,Will_用户遗嘱)=Boolean_true",
  "asks_about(Person_用户,Topic_确保遗嘱法律效力)=Boolean_true");
slot("BEAM-CAND-004", 4, "agent",
  "requires(Will_用户遗嘱,Req_列出资产和受益人)=Boolean_true",
  "requires(Will_用户遗嘱,Req_明确执行人任命)=Boolean_true",
  "requires(Will_用户遗嘱,Req_签名和见证)=Boolean_true",
  "recommends(Agent_助手,Action_请遗产规划律师审核遗嘱)=Boolean_true");
slot("BEAM-CAND-004", 5, "user",
  "guardian_of(Person_Stephanie,Child_Francis)=Boolean_true",
  "guardian_of(Person_Stephanie,Child_Michael)=Boolean_true",
  "date_of(Event_指定监护人)=Date(\"2024-04-28\")",
  "asks_about(Person_用户,Topic_监护安排对遗产计划的影响)=Boolean_true");
slot("BEAM-CAND-004", 5, "agent",
  "affects(Plan_监护安排,Plan_遗产计划)=Boolean_true",
  "requires(Plan_监护安排,Req_确认Stephanie意愿与适任性)=Boolean_true",
  "recommends(Agent_助手,Action_考虑备用监护人)=Boolean_true",
  "recommends(Agent_助手,Action_写清监护和继承资金管理)=Boolean_true");
