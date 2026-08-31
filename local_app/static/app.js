const DEFAULT_MODEL = "Qwen/Qwen3.5-35B-A3B";
const AVAILABLE_MODELS = [
  { id: "Qwen/Qwen3.5-35B-A3B", label: "Qwen 3.5 35B · 推荐" },
  { id: "deepseek-ai/DeepSeek-V3.2", label: "DeepSeek V3.2 · 高质量" },
  { id: "Qwen/Qwen3.5-27B", label: "Qwen 3.5 27B · 稳定" },
  { id: "Pro/zai-org/GLM-5.1", label: "GLM 5.1 Pro" },
  { id: "Pro/moonshotai/Kimi-K2.6", label: "Kimi K2.6 Pro" },
  { id: "MiniMaxAI/MiniMax-M2.5", label: "MiniMax M2.5" },
];

const PROMPT_STORAGE_KEY = "kbai_prompt_preferences_v4";
const DEFAULT_PROMPT_OVERRIDES = Object.freeze({
  qa: "你是智能接待助手。请用自然、清楚、可以直接对顾客说的话回答；先回应顾客当前问题，只补充一个最必要的信息，再给出一个明确的下一步。不要把知识库摘要、内部路由或幕后判断直接展示给顾客。",
  training: { customer: "你是情景陪练中的模拟顾客。请先回应员工最新一句，再继续相关对话。", coach: "你是情景陪练中的训练教练，只评价员工当前回答和此前公开信息。" },
  simulation: { customer: "你是实战考核中的模拟顾客。请先回应员工最新一句，再提出一个相关追问。", assessment: "你是企业培训考核官，只在对话结束后按评分表输出考核报告。" },
});
const PROMPT_PREFERENCE_DEFAULTS = Object.freeze({
  qa: "语气清楚、温和、简洁；使用通俗中文，表达有条理。",
  training: {
    customer: "口吻自然、口语化、简短；表达清楚且不重复。",
    coach: "语气简洁、清楚；使用分点和通俗中文。",
  },
  simulation: {
    customer: "口吻自然、口语化、简短；表达清楚且不重复。",
    assessment: "语言清楚、简洁；使用分点和通俗中文。",
  },
});

const CUSTOMER_REALISM_POLICY = `真人连续对话规则（高优先级）：
1. 把员工最新一句当作真实面对面交流。先判断它是在提问、解释、道歉、调整操作、暂停/终止、记录上报，还是安排下一步；顾客第一句话必须直接回应这个动作或问题。
2. 员工问了明确问题时先如实回答。设定里有答案就用普通顾客口吻回答；设定里没有就自然说“我没留意”“我不太确定”，不能拿另一个顾虑代替答案。
3. 员工给出具体动作或安排时，先表现出接受、拒绝、犹豫或确认一个细节。已经暂停就不要再问“过程中会不会难受”，已经说明记录上报就不要跳回价格或项目原理。
4. 不按轮次机械轮播隐藏异议。只有员工刚才已经回应完当前问题，而且新顾虑与这句话直接相关时，才自然带出一个新顾虑。
5. 保持人物个性但不要固定句式：谨慎型可以追问一个执行细节，直接型可以简短表态，焦虑型可以先说感受再确认安排。避免反复使用“这些专业的我不懂”“我主要还是想……”等万能句。
6. 回复应像现场真实顾客，通常 1—2 句、10—60 个汉字。可以有口语停顿、犹豫和情绪，但不能冗长、说教或像客服模板。
7. 输出前自检：回复是否回答了员工最新问题，是否承接了员工最新动作，是否与上一轮连得上。任一项不满足就重写，不能用无关隐藏异议凑数。`;

const POINT_WAVE_BEST_REPLY = "我理解您会担心。您做完点阵波后疼痛比原来更明显，我先把这个情况作为需要跟进的异常反应处理。今天我先为您暂停后续安排；麻烦您告诉我疼痛从什么时候开始、现在是否还在加重，以及有没有麻木、无力、发热、红肿或其他新不适。我会马上记录并请负责人跟进；如果症状明显、持续加重或伴随异常，我建议您尽快到医疗机构评估。";
// This version intentionally stays with the already disclosed pain change.
// It is used when an employee only raises an additional symptom hypothetically,
// so the coach never turns that condition into a customer fact.
const POINT_WAVE_PAIN_CONTEXT_REPLY = "我理解您会担心。您做完点阵波后疼痛比原来更明显，我先把这个情况作为需要跟进的异常反应处理。今天我先为您暂停后续安排；麻烦您告诉我疼痛从什么时候开始、目前的程度和变化。我会马上记录并请负责人跟进；如果症状明显、持续加重或出现其他新不适，我建议您尽快到医疗机构评估。";
const POINT_WAVE_IN_SESSION_PAUSE_REPLY = "收到，我们现在先停止操作。我先确认疼痛程度、具体感觉，以及有没有麻木、无力、红肿发热或其他新不适。";
const POINT_WAVE_POST_SERVICE_PAIN_REPLY = "我理解您会担心。服务后出现疼痛，尤其是一直不缓解、影响睡眠或越来越明显时，我先把这个情况作为需要跟进的异常反应处理。今天我先为您暂停同部位的后续安排；麻烦您告诉我疼痛从什么时候开始、现在的程度和变化，以及有没有麻木、无力、发热、红肿或其他新不适。我会马上记录并请负责人跟进；如果症状明显、持续或加重，我建议您尽快到医疗机构评估。";

const STATIC_POINT_WAVE_TIMING_PATTERN = /(?:做|打)(?:完|了|过)(?:了)?(?:后|之后|以后)?|刚(?:做|打)|(?:做|体验|接受)(?:了|过)?点阵波(?:后|之后|以后)|点阵波(?:结束|完成|操作)?(?:后|之后|以后)|(?:理疗|服务|体验|项目|治疗|操作|结束|完成)(?:后|之后|以后)|(?:完了|结束了)(?:后|之后|以后)|第二天|隔天|昨天做(?:的)?点阵波|点阵波(?:已经|曾经)(?:缓解|减轻|好了|恢复)/i;
const STATIC_POINT_WAVE_WORSENING_PATTERN = /更痛|更疼|更酸痛|更严重|(?:疼|痛)(?:得)?更厉害|(?:疼痛|痛感)(?:变得)?更严重|疼痛比.{0,8}严重|疼痛(?:加重|加剧|恶化)|痛感(?:变重|加剧|恶化)|越来越(?:痛|疼)|又(?:痛|疼)起来|是不是.{0,6}打坏/i;
const STATIC_POINT_WAVE_SEVERE_PATTERN = /(?:疼|痛)(?:得|到)?(?:受不了|不能忍|难以忍受|睡不着|无法入睡|痛醒)|(?:疼痛|痛感).{0,4}(?:受不了|不能忍|难以忍受|影响睡眠)|(?:剧痛|疼痛难忍|痛不欲生)|(?:疼痛|痛感)?(?:达到|有|是)?\s*(?:[7-9]|10)\s*分/i;
const STATIC_POINT_WAVE_PERSISTENT_PATTERN = /(?:一直|持续|连续|仍然|仍|还是|依然).{0,5}(?:疼|痛|酸痛)|(?:疼|痛|酸痛).{0,5}(?:一直|持续|连续)(?:了)?(?:一|两|俩|三|四|五|六|七|\d+)?(?:天|小时|晚|夜)?|(?:疼痛|痛感).{0,5}(?:没有|没|并未|未|尚未)(?:明显|完全)?(?:缓解|减轻|好转)|(?:一直|持续).{0,4}(?:没有|没|未|尚未)(?:缓解|减轻|好转)/i;
const STATIC_POINT_WAVE_NON_WORSENING_PATTERN = /(?:没有|没|并没有|并未|未|不再|不是)(?:感觉|觉得|变得|出现|继续|任何)?(?:比.{0,4})?(?:更痛|更疼|更酸痛|更严重|更厉害|疼痛加重|加重|加剧|恶化|越来越痛|越来越疼|疼痛|酸痛|痛感|痛得受不了|痛到睡不着|一直疼|持续疼)|(?:疼痛|痛感).{0,3}(?:没有|没|并未|未)(?:继续)?(?:加重|加剧|恶化|变重)|(?:疼痛|痛感).{0,4}(?:没变|没有变化|和之前一样|与之前一样|比之前轻|比原来轻)|(?:疼痛|痛感)(?:已经|现在|目前)?(?:明显|逐渐)?(?:减轻|缓解|好转)(?:了)?/i;
const STATIC_POINT_WAVE_RESOLVED_PATTERN = /(?:已经|现在|目前|后来)(?:已经)?(?:感觉)?(?:完全|基本|逐渐)?(?:不痛|不疼|不酸痛|缓解(?:了)?|减轻(?:了)?|好了|恢复(?:了)?)|(?:疼痛|痛感|酸痛)(?:已经|现在|目前)?(?:明显|逐渐)?(?:缓解|减轻|好转)(?:了)?|(?:不痛|不疼|不酸痛)(?:了|啦|，|。|！|？|\s|$)/i;
const STATIC_POINT_WAVE_PAIN_SIGNAL_PATTERN = /更痛|更疼|更严重|加重|加剧|恶化|受不了|睡不着|无法入睡|一直疼|持续.{0,4}(?:疼|痛)|没有缓解|没缓解|未缓解|尚未缓解|没有减轻|未减轻|疼痛|酸痛|痛感|打坏/i;
const STATIC_RED_FLAG_SYMPTOM_PATTERN = /胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|出冷汗|突发剧痛|突然剧痛|进行性麻木|麻木加重|持续麻木|腿麻|手麻|发麻|麻木|无力|大小便异常|会阴麻木|发热|红肿|不能负重/i;
const STATIC_RESOLVED_RED_FLAG_PATTERN = /(?:胸痛|胸闷|气短|呼吸困难|晕厥|手麻|腿麻|发麻|麻木|无力|大小便异常)(?:的情况)?(?:也|都|已经|现在|完全|基本)*(?:没有了|消失(?:了)?|不麻(?:了)?|缓解(?:了)?|减轻(?:了)?|好了|恢复(?:了)?)/gi;

function normalizeStaticPointWaveText(value = "") {
  return String(value || "").replace(/\s+/g, " ").trim().replaceAll("点振波", "点阵波")
    .replace(/小通(?:智能)?机器人|小通(?:光合)?智能探头|小通光合头/gi, "点阵波");
}

function normalizeStaticSafetyText(value = "") {
  let text = normalizeStaticPointWaveText(value);
  const replacements = [
    [/胸口(?:疼|痛)/gi, "胸痛"], [/胸口(?:发)?紧/gi, "胸闷"],
    [/(?:喘|呼吸)(?:不过|不上)气|呼吸不上来|透不过气/gi, "呼吸困难"],
    [/(?:晕倒|快晕|要晕)(?:了)?/gi, "晕厥"], [/(?:手|腿|胳膊|四肢)(?:没|没有)劲/gi, "无力"],
    [/胳膊抬不起来/gi, "手臂无力"], [/大小便失禁/gi, "大小便异常"], [/(?:脚|半边身子)(?:发)?麻/gi, "麻木"],
    [/(?:高)?发烧|高热/gi, "发热"], [/(?:喉咙|咽喉|喉头)(?:发)?紧/gi, "喉咙发紧"],
  ];
  replacements.forEach(([pattern, replacement]) => { text = text.replace(pattern, replacement); });
  return text;
}

function staticPointWaveAftercareHypothetical(value = "") {
  const text = normalizeStaticPointWaveText(value);
  const notTreated = /(?:我)?(?:还没|没有|没|尚未|未曾)(?:做|打|体验|接受)(?:过)?点阵波|点阵波(?:还没|没有|没|尚未|未曾)(?:做|打|体验|接受)/i.test(text);
  const prospectiveMarker = /如果|假如|假设|万一|会不会|是不是(?:会)?|是否(?:会)?|有可能|可能(?:会)?|担心(?:会)?|怕(?:会)?|会(?:导致|引起|出现)/i.test(text);
  const plainFutureQuestion = /会.{0,16}(?:更痛|更疼|更严重|加重|加剧|恶化|受不了|睡不着|无法入睡|一直疼|持续疼).{0,4}(?:吗|呢|\?|？|$)/i.test(text);
  const prospective = (prospectiveMarker || plainFutureQuestion)
    && STATIC_POINT_WAVE_PAIN_SIGNAL_PATTERN.test(text)
    && (/点阵波.{0,45}(?:如果|假如|假设|万一|会不会|是否|有可能|可能|担心|怕|会)/i.test(text)
      || /(?:如果|假如|假设|万一|会不会|是否|有可能|可能|担心|怕).{0,45}点阵波/i.test(text));
  const thirdParty = /朋友|别人|其他人|顾客|网友|网上|听说|有人/i.test(text);
  const actionableThirdParty = /怎么办|怎么处理|如何处理|该怎么|现在怎么办/i.test(text);
  return notTreated || prospective || (thirdParty && STATIC_POINT_WAVE_PAIN_SIGNAL_PATTERN.test(text) && !actionableThirdParty);
}

function staticPatternMatches(pattern, text) {
  const flags = pattern.ignoreCase ? "gi" : "g";
  return [...text.matchAll(new RegExp(pattern.source, flags))];
}

function staticPointWaveAftercareKind(value = "") {
  const text = normalizeStaticPointWaveText(value);
  if (!text.includes("点阵波") || !STATIC_POINT_WAVE_TIMING_PATTERN.test(text) || staticPointWaveAftercareHypothetical(text)) return null;
  const nonWorsening = staticPatternMatches(STATIC_POINT_WAVE_NON_WORSENING_PATTERN, text);
  const resolved = staticPatternMatches(STATIC_POINT_WAVE_RESOLVED_PATTERN, text);
  const events = [...nonWorsening, ...resolved].map((match) => [match.index, match.index + match[0].length, "resolved"]);
  [[STATIC_POINT_WAVE_WORSENING_PATTERN, "worsening"], [STATIC_POINT_WAVE_SEVERE_PATTERN, "pain"], [STATIC_POINT_WAVE_PERSISTENT_PATTERN, "pain"]].forEach(([pattern, kind]) => {
    staticPatternMatches(pattern, text).forEach((match) => {
      const start = match.index;
      const end = start + match[0].length;
      if (nonWorsening.some((negative) => start < negative.index + negative[0].length && negative.index < end)) return;
      events.push([start, end, kind]);
    });
  });
  if (events.length) {
    events.sort((first, second) => first[0] - second[0] || first[1] - second[1]);
    const latest = events.at(-1);
    return latest[2] === "resolved" ? null : latest[2];
  }
  const asksNormal = /正常不正常|正常吗|是否正常/i.test(text);
  const affirmativePain = /(?:做完|打完|理疗后|服务后|体验后|项目后|治疗后|点阵波后).{0,10}(?:疼|痛|酸痛)/i.test(text);
  return asksNormal && affirmativePain && !nonWorsening.length ? "pain" : null;
}

function isStaticPointWaveAftercareQuery(value = "") {
  return staticPointWaveAftercareKind(value) !== null;
}

function isStaticPointWaveAftercareHypothetical(value = "") {
  return staticPointWaveAftercareHypothetical(value);
}

function isStaticPointWaveAftercareResolved(value = "") {
  const text = normalizeStaticPointWaveText(value);
  return text.includes("点阵波") && STATIC_POINT_WAVE_TIMING_PATTERN.test(text)
    && !staticPointWaveAftercareHypothetical(text)
    && (STATIC_POINT_WAVE_NON_WORSENING_PATTERN.test(text) || STATIC_POINT_WAVE_RESOLVED_PATTERN.test(text))
    && staticPointWaveAftercareKind(text) === null;
}

function staticCurrentPointWaveAftercareResolved(current = "", context = "") {
  const currentText = normalizeStaticSafetyText(current);
  const contextText = normalizeStaticSafetyText(context);
  if (!contextText.includes("点阵波") || isStaticPointWaveAftercareQuery(currentText)) return false;
  const unresolved = STATIC_POINT_WAVE_PERSISTENT_PATTERN.test(currentText);
  const currentIndex = currentText ? contextText.lastIndexOf(currentText) : -1;
  const priorContext = currentIndex >= 0 ? contextText.slice(0, currentIndex) : contextText;
  const priorRedFlag = STATIC_RED_FLAG_SYMPTOM_PATTERN.test(staticAffirmedSafetyText(priorContext));
  const currentRedResolved = /(?:手麻|腿麻|麻木|发麻|无力|胸痛|胸闷|呼吸困难|晕厥)(?:的情况)?(?:也|都|已经|现在|完全|基本)*(?:不麻|没有了|消失|缓解|减轻|好了|恢复)|(?:疼痛|痛感).{0,3}(?:和|、).{0,3}(?:手麻|腿麻|麻木|无力).{0,5}(?:都|已经)?(?:缓解|消失|好了|恢复)/i.test(currentText);
  const resolved = STATIC_POINT_WAVE_RESOLVED_PATTERN.test(currentText) || currentRedResolved;
  return resolved && !unresolved && (!priorRedFlag || currentRedResolved);
}

function staticPointWaveAftercareReply(value = "") {
  return staticPointWaveAftercareKind(value) === "worsening" ? POINT_WAVE_BEST_REPLY : POINT_WAVE_POST_SERVICE_PAIN_REPLY;
}

const STATIC_POST_SERVICE_ADVERSE_SERVICE_PATTERN = /点阵波|点振波|小通(?:智能)?机器人|超V|超Ｖ|热动力|冰雕|轰脂|纳米喷射|胶原微水光|水光|智能提拉|磁波内雕|冰点脱毛|头皮养护|热玛吉|Fotona|4D|线雕|皮秒|祛斑|射频|玻尿酸|肉毒|超声炮|超声刀|光子|激光/i;
const STATIC_POST_SERVICE_ADVERSE_TIMING_PATTERN = /(?:做|打|用|体验|接受|进行|完成)(?:完|了|过)(?:了)?(?:后|之后|以后)?|(?:服务|项目|操作|体验|使用|治疗)(?:后|之后|以后)|术后|刚(?:做|打|用)|(?:点阵波|超V|超Ｖ|热动力|冰雕|轰脂|纳米喷射|胶原微水光|水光|智能提拉|磁波内雕|冰点脱毛|头皮养护|热玛吉|Fotona|4D|线雕|皮秒|祛斑|射频|玻尿酸|肉毒|超声炮|超声刀|光子|激光)(?:完|后|之后|以后)/i;
const STATIC_POST_SERVICE_ADVERSE_SYMPTOM_PATTERN = /过敏|荨麻疹|风团|红疹|疹子|肿痛|肿胀|红肿|(?:局部|一片|很|明显)?红(?:了)?|(?:脸|眼周|局部|皮肤)?(?:明显)?肿(?:了)?|水疱|水泡|渗出|渗液|流脓|脓液|破损|破溃|溃烂|瘙痒|(?:很)?痒|刺痛|灼热|火辣辣|(?:发)?烫|烧灼感|眼睑下垂|(?:皮肤|局部|脸)?(?:发白|发紫)|发炎|感染|硬结|(?:发烧|高烧|高热|发热)|喉咙发紧|咽喉(?:发)?紧|吞咽困难|不对称|(?:明显|持续)?(?:疼|痛)|麻木|发麻|无力|头晕|胸痛|胸闷|呼吸困难|晕厥/i;
const STATIC_POST_SERVICE_ADVERSE_NEGATED_PATTERN = /(?:没有|没|并没有|并未|未|不再|无)(?:明显|持续|任何|什么)?(?:过敏|荨麻疹|风团|红疹|疹子|肿痛|肿胀|红肿|(?:局部|一片|很|明显)?红(?:了)?|(?:脸|眼周|局部|皮肤)?(?:明显)?肿(?:了)?|水疱|水泡|渗出|渗液|流脓|脓液|破损|破溃|溃烂|瘙痒|(?:很)?痒|刺痛|灼热|火辣辣|(?:发)?烫|烧灼感|眼睑下垂|(?:皮肤|局部|脸)?(?:发白|发紫)|发炎|感染|硬结|(?:发烧|高烧|高热|发热)|喉咙发紧|咽喉(?:发)?紧|吞咽困难|不对称|(?:疼|痛)|麻木|发麻|无力|头晕|胸痛|胸闷|呼吸困难|晕厥)/gi;
const STATIC_POST_SERVICE_ADVERSE_RESOLVED_PATTERN = /(?:过敏|荨麻疹|风团|红疹|疹子|肿痛|肿胀|红肿|(?:局部|一片|很|明显)?红(?:了)?|(?:脸|眼周|局部|皮肤)?(?:明显)?肿(?:了)?|水疱|水泡|渗出|渗液|流脓|脓液|破损|破溃|溃烂|瘙痒|(?:很)?痒|刺痛|灼热|火辣辣|(?:发)?烫|烧灼感|眼睑下垂|(?:皮肤|局部|脸)?(?:发白|发紫)|发炎|感染|硬结|(?:发烧|高烧|高热|发热)|喉咙发紧|咽喉(?:发)?紧|吞咽困难|不对称|(?:明显|持续)?(?:疼|痛)|麻木|发麻|无力|头晕|胸痛|胸闷|呼吸困难|晕厥)(?:的情况)?(?:已经|已|现在|都|基本|完全|明显)*(?:不再|没有|没|消失|消了|消退|缓解|减轻|好了|恢复)|(?:已经|已|现在|都|基本|完全)*(?:脸|眼周|局部|皮肤)?(?:不再|没有|没|不)(?:过敏|荨麻疹|风团|红疹|疹子|肿痛|肿胀|红肿|(?:局部|一片|很|明显)?红(?:了)?|(?:脸|眼周|局部|皮肤)?(?:明显)?肿(?:了)?|水疱|水泡|渗出|渗液|流脓|脓液|破损|破溃|溃烂|瘙痒|(?:很)?痒|刺痛|灼热|火辣辣|(?:发)?烫|烧灼感|眼睑下垂|(?:皮肤|局部|脸)?(?:发白|发紫)|发炎|感染|硬结|(?:发烧|高烧|高热|发热)|喉咙发紧|咽喉(?:发)?紧|吞咽困难|不对称|(?:疼|痛)|麻木|发麻|无力|头晕|胸痛|胸闷|呼吸困难|晕厥)/gi;
const STATIC_POST_SERVICE_ADVERSE_HYPOTHETICAL_PATTERN = /如果|假如|假设|万一|会不会|是否(?:会)?|有可能|可能(?:会)?|担心(?:会)?|怕(?:会)?|听说|据说|网上说|有人说/i;
const STATIC_POST_SERVICE_ADVERSE_URGENT_PATTERN = /荨麻疹|风团|眼睑下垂|(?:皮肤|局部|脸)?(?:发白|发紫)|(?:发烧|高烧|高热|发热)|喉咙发紧|咽喉(?:发)?紧|吞咽困难|胸痛|胸闷|呼吸困难|晕厥|无力|麻木/i;
const STATIC_POST_SERVICE_ADVERSE_REPLY = "我理解您现在不舒服。我先把这个情况作为需要跟进的异常反应处理，今天我先为您暂停同部位的后续安排。请记录项目、时间、部位和症状变化，并尽快联系实施机构或有资质人员核实；症状明显、持续加重，或伴胸痛、呼吸困难、晕厥等情况时，请尽快到医疗机构评估。我也会同步负责人跟进。";
const STATIC_POST_SERVICE_ADVERSE_URGENT_REPLY = "您现在说的情况需要优先处理。请先不要继续同部位项目，也先不要自行处理；请尽快联系急救或前往医疗机构评估。我会立即记录项目、时间、部位和症状变化，并同步实施机构和负责人跟进。";

function staticPostServiceAdverseEvent(value = "") {
  const text = normalizeStaticSafetyText(value);
  // A clear same-turn point-wave recovery update is not a generic adverse
  // incident.  Any affirmed red flag is still handled by the earlier route.
  if (isStaticPointWaveAftercareResolved(text)) return false;
  if (text.includes("点阵波") && staticPointWaveAftercareHypothetical(text)) return false;
  const thirdParty = /朋友|别人|其他人|顾客|网友|网上|听说|有人/i.test(text);
  const actionableThirdParty = /怎么办|怎么处理|如何处理|该怎么|现在怎么办/i.test(text);
  if (thirdParty && !actionableThirdParty) return false;
  if (!STATIC_POST_SERVICE_ADVERSE_SERVICE_PATTERN.test(text) || !STATIC_POST_SERVICE_ADVERSE_TIMING_PATTERN.test(text)) return false;
  const affirmed = text.replace(STATIC_POST_SERVICE_ADVERSE_NEGATED_PATTERN, " ");
  const symptom = affirmed.match(STATIC_POST_SERVICE_ADVERSE_SYMPTOM_PATTERN);
  if (!symptom) return false;
  const resolved = [...affirmed.matchAll(STATIC_POST_SERVICE_ADVERSE_RESOLVED_PATTERN)];
  if (resolved.length) {
    const latestResolved = resolved.at(-1);
    const tail = affirmed.slice((latestResolved.index || 0) + latestResolved[0].length);
    if (!STATIC_POST_SERVICE_ADVERSE_SYMPTOM_PATTERN.test(tail)) return false;
  }
  const hypothetical = text.match(STATIC_POST_SERVICE_ADVERSE_HYPOTHETICAL_PATTERN);
  return !hypothetical || Number(hypothetical.index) > Number(symptom.index);
}

function matchesStaticPointWaveBestReply(value = "") {
  const comparable = (text) => String(text || "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, "");
  return comparable(value) === comparable(POINT_WAVE_BEST_REPLY);
}

function normalizePromptText(value, fallback = "") {
  const text = String(value ?? "").replace(/\u0000/g, "").trim().slice(0, 2000);
  return text || fallback;
}

const PROMPT_PREFERENCE_FUNCTION_PATTERN = /(?:忽略|无视|覆盖|改写|取消固定|绕过|越过|不要输出\s*json|不要遵守|system|assistant|developer|role\s*=|hidden_information|information_release_rules|提示词|prompt|json|schema|字段|输出|角色|指令|规则|推荐|推介|安排|销售|营销|项目|产品|套餐|次数|疗程|服务|体验|设备|保证|承诺|疗效|效果|见效|有效|治愈|根治|反弹|改善|药品?|处方|剂量|用药|服用|口服|注射|停药|换药|诊断|病因|治疗|医疗建议|暂停|停止|继续|操作|执行|开始|结束|评分|考核|得分|分数|评估|检索|路由|知识库|课程|资料|文档|引用)/i;
const PROMPT_STYLE_TERMS = Object.freeze([
  "避免重复", "少用重复", "不重复", "避免缩写", "少用缩写", "避免术语", "少用术语", "不使用术语", "多说一点", "详细一点", "展开一点", "多一些", "少一些",
  "有条理", "第一人称", "第二人称", "小标题", "分点", "分段", "段落", "条目", "清单",
  "语气", "口吻", "措辞", "表达", "风格", "语言", "中文", "英文", "文字", "用词", "篇幅", "字数", "长度",
  "简洁", "简短", "精炼", "温和", "友好", "专业", "自然", "口语", "口语化", "正式", "清楚", "清晰", "直接",
  "通俗", "易懂", "克制", "稳重", "耐心", "礼貌", "亲切", "平实", "中性", "轻松", "积极", "客观", "尊重", "共情",
  "tone", "style", "concise", "brief", "clear", "friendly", "professional", "natural", "formal", "plain", "chinese", "english", "bullet",
]);
const PROMPT_STYLE_FILLERS = Object.freeze([
  "大约", "左右", "以内", "之间", "采用", "使用", "控制", "保持", "尽量", "可以", "不要", "请", "用", "以", "更", "一些", "一点", "偏",
  "的", "地", "得", "和", "与", "或", "并", "且", "不", "别", "为", "在", "约", "每", "句", "段", "个", "字", "条", "写得", "说得", "让", "成", "是", "太", "很", "较", "都", "可", "内", "到", "至",
  "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
]);

function isStyleOnlyPromptPreference(text = "") {
  if (!text || PROMPT_PREFERENCE_FUNCTION_PATTERN.test(text)) return false;
  let remainder = String(text).toLowerCase();
  [...PROMPT_STYLE_TERMS, ...PROMPT_STYLE_FILLERS].sort((a, b) => b.length - a.length).forEach((term) => {
    remainder = remainder.replaceAll(term.toLowerCase(), "");
  });
  remainder = remainder.replace(/[\s\d０-９，,、。；;：:！？!?（）()【】\[\]{}<>《》"'`~—\-]+/g, "");
  return !/[\u4e00-\u9fffA-Za-z]/.test(remainder);
}

function sanitizePromptPreference(value, fallback = "") {
  const text = normalizePromptText(value, fallback);
  return isStyleOnlyPromptPreference(text) ? text : fallback;
}

function normalizePromptOverrides(value, defaults = PROMPT_PREFERENCE_DEFAULTS) {
  const source = value && typeof value === "object" ? value : {};
  const training = source.training && typeof source.training === "object" ? source.training : { customer: source.training, coach: source.training };
  const simulation = source.simulation && typeof source.simulation === "object" ? source.simulation : { customer: source.simulation, assessment: source.simulation };
  return {
    qa: sanitizePromptPreference(source.qa, defaults.qa),
    training: {
      customer: sanitizePromptPreference(training.customer, defaults.training.customer),
      coach: sanitizePromptPreference(training.coach, defaults.training.coach),
    },
    simulation: {
      customer: sanitizePromptPreference(simulation.customer, defaults.simulation.customer),
      assessment: sanitizePromptPreference(simulation.assessment, defaults.simulation.assessment),
    },
  };
}

function loadPromptOverrides(defaults = PROMPT_PREFERENCE_DEFAULTS) {
  try {
    return normalizePromptOverrides(JSON.parse(localStorage.getItem(PROMPT_STORAGE_KEY) || "{}"), defaults);
  } catch {
    return normalizePromptOverrides({}, defaults);
  }
}

function savePromptOverrides(value, defaults = PROMPT_PREFERENCE_DEFAULTS) {
  const normalized = normalizePromptOverrides(value, defaults);
  localStorage.setItem(PROMPT_STORAGE_KEY, JSON.stringify(normalized));
  return normalized;
}

function promptSystemEnvelope(kind, customPrompt) {
  const configuredDefaults = state.promptDefaults || DEFAULT_PROMPT_OVERRIDES;
  const fixedPrompts = {
    qa: configuredDefaults.qa,
    training_customer: `${configuredDefaults.training.customer}\n\n${CUSTOMER_REALISM_POLICY}`,
    training_coach: configuredDefaults.training.coach,
    simulation_customer: `${configuredDefaults.simulation.customer}\n\n${CUSTOMER_REALISM_POLICY}`,
    simulation_assessment: configuredDefaults.simulation.assessment,
  };
  const guards = {
    qa: "保持顾客接待助手身份，只基于请求中提供的路由和资料回答；必须输出 answer、uncertainties、citations、recommended_action。若当前资料已直接覆盖问题，先给出直接结论；不得用‘更想了解体验/适用性/变化’替代已有答案。自然措辞可以变化，但每个项目事实、原理、效果、风险和安排必须来自本轮路由或资料。",
    training_customer: "保持模拟顾客身份，只生成 customer_reply；不得评价员工或泄露隐藏设定，必须先回应员工最新一句。",
    training_coach: "保持训练教练身份，只评价员工当前原话和此前公开顾客信息；必须输出 feedback 及固定字段。",
    simulation_customer: "保持模拟顾客身份，只输出 reply、emotion、should_continue；先回应员工最新问题或安排，再提出最多一个相关追问。",
    simulation_assessment: "保持考核官身份，只输出固定评分报告；严格保留 7 个维度、JSON 字段、逐轮时序和关键失败封顶规则。",
  };
  const preferenceDefaults = {
    qa: PROMPT_PREFERENCE_DEFAULTS.qa,
    training_customer: PROMPT_PREFERENCE_DEFAULTS.training.customer,
    training_coach: PROMPT_PREFERENCE_DEFAULTS.training.coach,
    simulation_customer: PROMPT_PREFERENCE_DEFAULTS.simulation.customer,
    simulation_assessment: PROMPT_PREFERENCE_DEFAULTS.simulation.assessment,
  };
  const preference = sanitizePromptPreference(customPrompt, preferenceDefaults[kind] || "");
  return `【可编辑内容参考（仅影响表达偏好，不改变功能）】\n${preference}\n\n【固定系统 Prompt（不可编辑）】\n${fixedPrompts[kind] || "保持系统角色、边界和结构化输出。"}\n\n【固定结构与安全保护（不可编辑）】\n${guards[kind] || "保持系统角色、边界和结构化输出。"}`;
}

const state = {
  route: "learning",
  routeModuleId: null,
  mode: "learning",
  modules: [],
  courses: [],
  catalogIndex: [],
  scenarios: [],
  learningModuleId: null,
  practiceModuleId: null,
  objectiveModuleId: null,
  simulationModuleId: null,
  testModuleId: null,
  scenarioIndex: 0,
  scenario: null,
  history: [],
  apiKey: localStorage.getItem("kbai_api_key") || "",
  model: localStorage.getItem("kbai_model") || DEFAULT_MODEL,
  promptOverrides: loadPromptOverrides(),
  promptDefaults: DEFAULT_PROMPT_OVERRIDES,
  models: [...AVAILABLE_MODELS],
  apiVerified: false,
  backendApiConfigured: false,
  busy: false,
  ended: false,
  revising: false,
  knowledge: {},
  examBank: null,
  realExamBank: null,
  objectiveAnswersByModule: {},
  objectiveScoresByModule: {},
  simulationScoresByModule: {},
  requestSerial: 0,
  voiceCapture: null,
  voiceRequestSerial: 0,
};

const $ = (id) => document.getElementById(id);
const els = {
  modeButtons: document.querySelectorAll(".mode-button"),
  modeBreadcrumb: $("mode-breadcrumb"),
  pageTitle: $("page-title"),
  pageDescription: $("page-description"),
  learningHubPage: $("learning-hub-page"),
  assessmentHubPage: $("assessment-hub-page"),
  moduleGatewayPage: $("module-gateway-page"),
  gatewayBack: $("gateway-back"),
  gatewayTag: $("gateway-tag"),
  gatewayTitle: $("gateway-title"),
  gatewayDescription: $("gateway-description"),
  moduleRouteGrid: $("module-route-grid"),
  learningPage: $("learning-page"),
  trainingPage: $("training-page"),
  testPage: $("test-page"),
  qaPage: $("qa-page"),
  learningSelect: $("learning-module-select"),
  practiceSelect: $("practice-module-select"),
  testSelect: $("test-module-select"),
  learningSummary: $("learning-module-summary"),
  learningChapters: $("learning-chapters"),
  trainingScenario: $("training-scenario-frame"),
  testScenario: $("test-scenario-frame"),
  testRouteBack: $("test-route-back"),
  testRouteTag: $("test-route-tag"),
  testRouteTitle: $("test-route-title"),
  testRouteDescription: $("test-route-description"),
  conversationStage: $("conversation-stage"),
  conversationAvatar: $("conversation-avatar"),
  conversationKicker: $("conversation-kicker"),
  conversationTitle: $("conversation-title"),
  messages: $("messages"),
  input: $("message-input"),
  voiceInput: $("voice-input-button"),
  voiceInputLabel: $("voice-input-label"),
  send: $("send-button"),
  finish: $("finish-session"),
  turnCount: $("turn-count"),
  composerHint: $("composer-hint"),
  apiStatus: $("api-status"),
  healthNumber: $("health-number"),
  courseModalContent: $("course-modal-content"),
  toast: $("toast"),
  clearChat: $("clear-chat"),
};

const modeCopy = {
  learning: {
    nav: "学习与陪练 / 课程学习",
    title: "课程学习",
    description: "按章节学习项目知识、服务流程和接待表达。",
    kicker: "",
    conversation: "",
    hint: "",
  },
  training: {
    nav: "学习与陪练 / 情景陪练",
    title: "情景陪练",
    description: "接待模拟顾客，及时发现并改进表达。",
    kicker: "情景陪练",
    conversation: "接待模拟顾客",
    hint: "发送后即可查看本轮反馈和参考表达",
  },
  test: {
    nav: "实战考核",
    title: "实战考核",
    description: "独立完成模拟接待，查看能力评分和改进建议。",
    kicker: "实战考核",
    conversation: "独立接待模拟顾客",
    hint: "请按真实接待方式独立完成对话",
  },
  qa: {
    nav: "智能接待",
    title: "智能接待",
    description: "根据企业知识库，为你提供专业接待建议。",
    kicker: "接待问答助手",
    conversation: "输入顾客的问题",
    hint: "回答会附上相关课程，方便继续学习",
  },
};

const ROUTE_CONFIG = {
  learning: {
    area: "learning", mode: "learning", screen: "hub",
    nav: "学习与陪练", title: "学习与陪练", description: "学知识、练接待，让每一次服务更专业。",
  },
  "learning/course": {
    area: "learning", mode: "learning", screen: "activity", parent: "learning",
    tag: "课程学习", nav: "学习与陪练 / 课程学习", title: "课程学习", gatewayTitle: "选择课程模块",
    pageDescription: "系统学习项目知识、服务流程和标准表达。", description: "从一个模块开始，按章节学习相关课程。", workspaceDescription: "按章节学习本模块的课程与服务要点。", action: "查看课程",
  },
  "learning/practice": {
    area: "learning", mode: "training", screen: "activity", parent: "learning",
    tag: "情景陪练", nav: "学习与陪练 / 情景陪练", title: "情景陪练", gatewayTitle: "选择陪练主题",
    pageDescription: "在真实顾客情景中练习接待，获得即时反馈。", description: "选择想练习的主题，马上开始接待模拟顾客。", workspaceDescription: "选择顾客场景，练习接待并获得即时反馈。", action: "开始陪练",
  },
  exam: {
    area: "exam", mode: "test", screen: "hub",
    nav: "实战考核", title: "实战考核", description: "通过答题与模拟接待，检验知识掌握和实际应用能力。",
  },
  "exam/objective": {
    area: "exam", mode: "test", screen: "activity", parent: "exam",
    tag: "知识考试", nav: "实战考核 / 客观题考试", title: "客观题考试", gatewayTitle: "选择考试模块",
    pageDescription: "完成知识测试，巩固关键业务要点。", description: "选择一个知识模块，完成填空、选择和 FAQ 关键词问答。", workspaceDescription: "完成当前模块全部题目，交卷后查看成绩和解析。", action: "开始答题",
  },
  "exam/simulation": {
    area: "exam", mode: "test", screen: "activity", parent: "exam",
    tag: "模拟接待", nav: "实战考核 / 模拟顾客考核", title: "模拟顾客考核", gatewayTitle: "选择考核主题",
    pageDescription: "独立完成模拟接待，检验沟通与风险意识。", description: "选择一个接待主题，完成模拟顾客对话。", workspaceDescription: "完成至少 4 轮接待对话，结束后查看实战评分。", action: "开始考核",
  },
  qa: {
    area: "qa", mode: "qa", screen: "workspace",
    nav: "智能接待", title: "智能接待", description: "根据企业知识库，为你提供专业接待建议。",
  },
};

const VALID_ROUTES = new Set(Object.keys(ROUTE_CONFIG));
const LEGACY_ROUTES = {
  learn: "learning",
  assessment: "exam",
  training: "learning/practice",
  test: "exam",
};

const STATIC_PAGES = window.location.hostname.endsWith(".github.io");
const staticAsset = (name) => STATIC_PAGES ? `./${name}` : `/static/${name}`;
let staticDataPromise = null;
const modalReturnFocus = new Map();

function parseJsonl(text) {
  return text.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

function mergePointWaveFaqExam(examBank, pointWaveFaqExam) {
  if (!examBank || !Array.isArray(examBank.modules)) return examBank;
  const questions = Array.isArray(pointWaveFaqExam?.questions) ? pointWaveFaqExam.questions : [];
  const moduleId = String(pointWaveFaqExam?.module_id || "MOD-03");
  const target = examBank.modules.find((item) => item.id === moduleId);
  if (target) target.faq_keyword_answers = questions;
  return examBank;
}

async function loadStaticData() {
  if (!staticDataPromise) {
    staticDataPromise = Promise.all([
      fetch("./data/scenario_library.jsonl").then((response) => response.text()).then(parseJsonl),
      fetch("./data/rag_documents.jsonl").then((response) => response.text()).then(parseJsonl),
      fetch("./data/common_qa_catalog.jsonl").then((response) => response.text()).then(parseJsonl),
      fetch("./data/common_qa_excel_catalog.jsonl").then((response) => response.text()).then(parseJsonl),
      fetch("./data/scoring_rubric.json").then((response) => response.json()),
      fetch("./data/customer_service_methodology.json").then((response) => response.json()),
      fetch("./data/comprehensive_exam_bank.json").then((response) => response.json()),
      fetch("./data/point_wave_faq_exam.json").then((response) => response.json()),
      fetch("./data/prompt_defaults.json").then((response) => response.json()),
    ]).then(([scenarios, documents, commonQa, commonQaExcel, rubric, methodology, examBank, pointWaveFaqExam, promptDefaults]) => ({
      scenarios,
      documents,
      commonQa: [...commonQa, ...commonQaExcel],
      rubric,
      methodology,
      examBank: mergePointWaveFaqExam(examBank, pointWaveFaqExam),
      promptDefaults,
    }));
  }
  return staticDataPromise;
}

function publicStaticDocument(document) {
  const metadata = document.metadata || {};
  const course = resolveReferenceCourse(document);
  const module = course ? moduleById(course.module_id) : null;
  return {
    document_id: document.document_id,
    course_id: course?.id || metadata.course_id || "",
    title: course?.title || metadata.title || document.document_id || "知识库资料",
    module: module?.short_name || module?.title || metadata.module || metadata.domain || "知识库",
    chapter: course?.group_title || metadata.chapter || "",
  };
}

function staticMatchesAny(text, patterns = []) {
  return patterns.some((pattern) => {
    try { return new RegExp(pattern, "i").test(text); } catch { return false; }
  });
}

const STATIC_NEGATED_RED_FLAG_PATTERN = /(?:没有|没|并没有|并无|尚无|未见|未出现|未发生|没出现|不伴有?|否认|无)(?:(?:任何|什么|一点儿?|明显|持续|进行性|新发|突然)){0,2}(?:胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|出冷汗|突发剧痛|突然剧痛|腿(?:部)?(?:新发|新|发)?麻|手(?:臂)?(?:新发|新|发)?麻|胳膊(?:新发|新|发)?麻|发麻|麻木|无力|大小便异常|会阴麻木|发热|红肿|头晕|灼热|不舒服|不适)(?:(?:(?:、|或|和|及|以及)?)(?:(?:任何|什么|一点儿?|明显|持续|进行性|新发|突然)){0,2}(?:胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|出冷汗|突发剧痛|突然剧痛|腿(?:部)?(?:新发|新|发)?麻|手(?:臂)?(?:新发|新|发)?麻|胳膊(?:新发|新|发)?麻|发麻|麻木|无力|大小便异常|会阴麻木|发热|红肿|头晕|灼热|不舒服|不适))*/gi;

function staticAffirmedSafetyText(text) {
  let candidate = normalizeStaticSafetyText(text).replace(STATIC_NEGATED_RED_FLAG_PATTERN, " ");
  candidate = candidate.replace(STATIC_RESOLVED_RED_FLAG_PATTERN, " ");
  const parts = candidate.split(/([，。；！？,.;!?])/);
  const markerPattern = /如果|假如|假设|万一|会不会|是否(?:会)?|有可能|可能(?:会)?|担心(?:会)?|怕(?:会)?|会(?:导致|引起|出现)|听说|据说|网上说|有人说/i;
  for (let index = 0; index < parts.length; index += 2) {
    const clause = parts[index];
    let marker = clause.match(markerPattern);
    if (!marker) {
      const plainFuture = clause.match(/会(?=.{0,12}(?:吗|呢|真的|\?|？|$))/i);
      if (plainFuture && STATIC_RED_FLAG_SYMPTOM_PATTERN.test(clause.slice(plainFuture.index))) marker = plainFuture;
    }
    if (marker) {
      const start = marker.index;
      parts[index] = clause.slice(0, start) + clause.slice(start).replace(new RegExp(STATIC_RED_FLAG_SYMPTOM_PATTERN.source, "gi"), " ");
    }
  }
  return parts.join("");
}

function staticIntentMatches(text, intent) {
  const candidate = intent?.id === "INTENT-RED-FLAG" ? staticAffirmedSafetyText(text) : text;
  if (intent?.id === "INTENT-AFTERCARE" && (isStaticPointWaveAftercareResolved(candidate) || isStaticPointWaveAftercareHypothetical(candidate))) return false;
  if (intent?.id === "INTENT-AFTERCARE" && candidate.includes("点阵波")) {
    if (isStaticPointWaveAftercareQuery(candidate)) return true;
    const affirmed = staticAffirmedSafetyText(candidate);
    if (!/头晕|灼热|红肿|发热|麻木|发麻|无力|不舒服|不适/i.test(affirmed)) return false;
  }
  return staticMatchesAny(candidate, intent?.patterns || []);
}

function uniqueStaticItems(values = []) {
  return [...new Set(values.filter(Boolean))];
}

function staticRouteCustomerQuestion(query, methodology = {}) {
  const text = normalizeStaticSafetyText(query);
  const intents = [...(methodology.intent_routes || [])].sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0));
  let matchedIntent = intents.find((item) => staticIntentMatches(text, item)) || null;
  const topics = (methodology.topic_routes || []).filter((item) => staticMatchesAny(text, item.patterns));
  const drugTerms = /药|用药|口服|服用|注射|针剂|剂量|停药|换药|GLP.?1|贝那鲁肽|司美格鲁肽|利拉鲁肽|减肥针|美妥|细美宝/i.test(text);
  const projectTopic = topics.some((topic) => new Set(["MOD-03", "MOD-04", "MOD-05", "MOD-07", "MOD-08", "MOD-09", "MOD-10"]).has(topic.module_id));
  const namedService = /项目|设备|体验|热玛吉|超V|冰雕|点阵波|点振波|热动力|轰脂|纳米喷射|胶原微水光|磁波内雕|智能提拉|冰点脱毛|头皮养护|射频|超声炮|Fotona|4D|线雕|水光|皮秒|祛斑|私密|盆底/i.test(text);
  if (matchedIntent?.id === "INTENT-DRUG" && !drugTerms && (projectTopic || namedService)) {
    matchedIntent = intents.find((item) => item.id === "INTENT-SUITABILITY") || null;
  }
  const fallback = methodology.default_route || {};
  const intent = matchedIntent || (topics.length ? {
    id: "INTENT-INFORMATION",
    label: topics[0].label || "项目原理、流程与一般咨询",
    primary_module_id: "DYNAMIC",
    support_module_ids: [],
    course_ids: [],
    focus: topics[0].recommended_next || "使用对应项目课程回答。",
    stop_sales: false,
  } : {
    id: fallback.intent_id || "INTENT-INFORMATION",
    label: fallback.intent_label || "一般需求咨询",
    primary_module_id: fallback.primary_module_id || "MOD-01",
    support_module_ids: fallback.support_module_ids || ["MOD-01"],
    course_ids: fallback.course_ids || [],
    focus: fallback.focus || "先确认顾客目标和必要安全信息。",
    stop_sales: Boolean(fallback.stop_sales),
  });
  const topicPrimary = topics[0]?.module_id || null;
  const intentPrimary = intent.primary_module_id;
  const primaryModuleId = !matchedIntent && topicPrimary ? topicPrimary : intentPrimary === "DYNAMIC" ? (topicPrimary || fallback.primary_module_id || "MOD-01") : (intentPrimary || topicPrimary || fallback.primary_module_id || "MOD-01");
  const supportModuleIds = [];
  if (topicPrimary && topicPrimary !== primaryModuleId) supportModuleIds.push(topicPrimary);
  topics.forEach((topic) => {
    supportModuleIds.push(...(topic.support_module_ids || []));
    if (topic.module_id !== primaryModuleId) supportModuleIds.push(topic.module_id);
  });
  supportModuleIds.push(...(intent.support_module_ids || []));
  if (primaryModuleId !== "MOD-01") supportModuleIds.push("MOD-01");
  const validModuleIds = new Set(state.modules.map((item) => item.id));
  const cleanSupportIds = uniqueStaticItems(supportModuleIds).filter((id) => validModuleIds.has(id) && id !== primaryModuleId);
  const courseIds = [...(intent.course_ids || [])];
  const knowledgePoints = [];
  topics.forEach((topic) => {
    courseIds.push(...(topic.course_ids || []));
    knowledgePoints.push(...(topic.knowledge_points || []));
  });
  if (!topics.length && !matchedIntent) courseIds.push(...(fallback.course_ids || []));
  if (intent.stop_sales) courseIds.push("COURSE-NKB-001", "COURSE-NKB-002", "COURSE-NKB-003", "COURSE-NKB-004");
  const validCourseIds = new Set(state.courses.map((item) => item.id));
  const cleanCourseIds = uniqueStaticItems(courseIds).filter((id) => validCourseIds.has(id));
  const moduleByRouteId = (id) => state.modules.find((item) => item.id === id);
  const courseByRouteId = (id) => state.courses.find((item) => item.id === id);
  const objectionIntents = new Set(["INTENT-PRICE", "INTENT-RESULT", "INTENT-COMPARISON", "INTENT-DECISION"]);
  const methodStep = intent.stop_sales ? "安全确认与停止分流" : objectionIntents.has(intent.id) ? "承接异议、依据回应并确认下一步" : intent.id === "INTENT-SUITABILITY" ? "安全确认后再解释选择" : topics.length ? "定位项目、补充必要信息并解释选择" : "了解目标并完成问题定位";
  let recommendedNext = matchedIntent?.recommended_next || topics.find((item) => item.recommended_next)?.recommended_next || fallback.focus || "先确认顾客目标和必要安全信息。";
  if (intent.id === "INTENT-SUITABILITY") {
    recommendedNext = ({
      "MOD-03": "先确认想改善的问题、持续时间、服务部位和必要安全信息，再说明项目边界。",
      "MOD-04": "先确认想改善的问题、对温热的感受和必要安全信息，再说明体验边界。",
      "MOD-05": "先确认想改善的部位、当前身体状态和必要安全信息，再核对具体塑形项目。",
      "MOD-07": "先确认想改善的部位、局部皮肤与近期项目，再核对塑形项目的体验和安全边界。",
      "MOD-08": "先确认当前皮肤状态、近期项目和必要安全信息，再核对具体项目。",
      "MOD-09": "先确认具体医美项目、近期治疗史、植入物和当前状态，再由有资质人员核对。",
      "MOD-10": "先保护隐私并确认顾客主动提出的目标、当前症状和必要安全信息。",
    })[primaryModuleId] || "先确认当前状态、顾客目标和必要安全信息，再说明体验边界。";
  }
  return {
    intent_id: intent.id || "INTENT-INFORMATION",
    intent_label: intent.label || "一般需求咨询",
    topic_ids: topics.map((item) => item.id),
    topic_labels: topics.map((item) => item.label).filter(Boolean),
    primary_module_id: primaryModuleId,
    primary_module: moduleByRouteId(primaryModuleId)?.title || "新客接待与需求洞察",
    support_module_ids: cleanSupportIds,
    support_modules: cleanSupportIds.map((id) => moduleByRouteId(id)?.title).filter(Boolean),
    required_course_ids: cleanCourseIds,
    required_courses: cleanCourseIds.map((id) => courseByRouteId(id)?.title).filter(Boolean),
    knowledge_points: uniqueStaticItems(knowledgePoints).slice(0, 6),
    focus: intent.focus || fallback.focus || "先确认顾客目标和必要安全信息。",
    recommended_next: recommendedNext,
    method_step: methodStep,
    stop_sales: Boolean(intent.stop_sales),
  };
}

function publicStaticRoute(route = {}) {
  return {
    intent: route.intent_label || "一般需求咨询",
    primary_module: route.primary_module || "新客接待与需求洞察",
    supporting_modules: route.support_modules || [],
    knowledge_points: (route.knowledge_points || []).slice(0, 4),
    courses: (route.required_courses || []).slice(0, 5),
    method_step: route.method_step || "了解目标并完成问题定位",
    stop_sales: Boolean(route.stop_sales),
  };
}

function staticRouteContext(route = {}) {
  return JSON.stringify({
    问题类型: route.intent_label,
    主要知识模块: route.primary_module,
    辅助知识模块: route.support_modules || [],
    必须调用课程: route.required_courses || [],
    回答重点: route.focus,
    项目或主题知识点: route.knowledge_points || [],
    推荐下一步: route.recommended_next,
    是否停止销售推进: Boolean(route.stop_sales),
  });
}

function staticQaQuery(message, history = []) {
  const current = String(message || "").replace(/\s+/g, " ").trim();
  const priorQuestions = history.filter((item) => item?.role === "user").slice(-3).map((item) => item.content);
  const pointContext = priorQuestions.some((item) => normalizeStaticPointWaveText(item).includes("点阵波"));
  const namedServiceContext = priorQuestions.some((item) => STATIC_POST_SERVICE_ADVERSE_SERVICE_PATTERN.test(normalizeStaticSafetyText(item)));
  const treatedServiceContext = priorQuestions.some((item) => {
    const prior = normalizeStaticSafetyText(item);
    return STATIC_POST_SERVICE_ADVERSE_SERVICE_PATTERN.test(prior) && STATIC_POST_SERVICE_ADVERSE_TIMING_PATTERN.test(prior);
  });
  const shortStatusUpdate = pointContext && current.length <= 36
    && /更痛|更疼|更严重|(?:疼痛|痛感)?(?:加重|加剧|恶化)(?:了)?|一直(?:没|没有|未)?缓解|仍未缓解|尚未缓解|还是很痛|仍然很痛|痛得受不了|痛到睡不着|已经缓解|已经减轻|已经不痛|不疼了|手麻还在|麻木还在|无力还在|(?:疼痛|手麻|麻木|无力).{0,8}(?:都|也)?(?:缓解|消失|好了|恢复)/i.test(current);
  const contextual = /^(?:那|这个|这种|它|刚才|如果|那么|可是|但是|她追问|他追问|顾客(?:又)?问|顾客追问|对方(?:又)?问|对方追问)/.test(current)
    || /^(?:那我|我)?(?:现在|接下来)?(?:应该|该)?(?:怎么办|做什么)(?:呢)?[？?]?$/.test(current)
    || /^(?:可以吗|为什么|多少钱|多少|多久|呢)[？?]?$/.test(current)
    || shortStatusUpdate
    || (namedServiceContext && current.length <= 32
      && /^(?:那|它|这个|这种)?(?:的)?(?:副作用|不良反应|风险|禁忌|恢复期|疼痛|红肿|肿胀|过敏|效果|适合吗?|能做吗?)(?:呢|吗|怎么样|如何|有什么|有吗)?[？?]?$/i.test(current));
  const postServiceSymptomFollowUp = treatedServiceContext && current.length <= 48
    && (STATIC_POST_SERVICE_ADVERSE_SYMPTOM_PATTERN.test(normalizeStaticSafetyText(current))
      || /^(?:那|现在|这个|这种)?(?:该|应该)?(?:怎么办|怎么处理|如何处理)(?:呢)?[？?]?$/i.test(current));
  if (!contextual && !postServiceSymptomFollowUp) return current;
  return [...priorQuestions, current].filter(Boolean).join(" ");
}

const COMMON_QA_NOISE_RE = /请问|我想(?:问|了解)|想问一下|请教一下|什么是|是什么|为什么|为啥|怎么回事|如何|怎么|怎么办|能不能|可以吗|是否|吗|呢|呀|啊|的|一下/gi;
const COMMON_QA_SYNONYMS = [
  ["点振波", "点阵波"],
  ["头疼", "头不适"],
  ["头痛", "头不适"],
  ["疼痛", "不适"],
  ["疼", "不适"],
  ["痛", "不适"],
  ["为啥", "为什么"],
  ["咋", "怎么"],
];

function normalizeStaticCommonQaText(value) {
  let text = String(value || "").replace(/\s+/g, "").toLowerCase();
  COMMON_QA_SYNONYMS.forEach(([source, target]) => { text = text.replaceAll(source, target); });
  return text.replace(/[^a-z0-9\u4e00-\u9fff]+/g, "");
}

function staticCommonQaCoreText(value) {
  return normalizeStaticCommonQaText(value).replace(COMMON_QA_NOISE_RE, "");
}

function staticCommonQaMatchTerms(value) {
  const text = staticCommonQaCoreText(value);
  const terms = new Set(text.match(/[a-z0-9_]+/g) || []);
  for (let index = 0; index < text.length - 1; index += 1) {
    const pair = text.slice(index, index + 2);
    if (/^[\u4e00-\u9fff]{2}$/.test(pair)) terms.add(pair);
  }
  return terms;
}

const COMMON_QA_INTENT_PATTERNS = {
  definition: /什么是|是什么|原理|定位|怎么工作|作用是什么/i,
  adverse_effect: /副作用|不良反应|反应|不适|疼痛|痛|酸胀|刺痛|更痛|更疼|淤青|青紫|肿|麻木|发麻|头晕|耳鸣|犯困|恶心|红肿|发热|过敏/i,
  suitability: /能做|可以做|适合|风险|危险|禁忌|术后|疾病|结节|孕|哺乳|心脏|高血压/i,
  efficacy: /有效|效果|改善|见效|一次|几次|多久|保证|反弹|好不好/i,
  comparison: /区别|比较|哪个|联合|同时|和.+区别/i,
  price: /价格|多少钱|收费|贵|预算|费用/i,
  process: /怎么做|如何做|操作|顺序|安排|部位|频率|次数|流程/i,
};

function staticCommonQaIntents(value) {
  const text = String(value || "");
  return new Set(Object.entries(COMMON_QA_INTENT_PATTERNS).filter(([, pattern]) => pattern.test(text)).map(([name]) => name));
}

function staticCommonQaScore(query, row) {
  const queryCore = staticCommonQaCoreText(query);
  const questionCore = staticCommonQaCoreText(row?.question);
  if (queryCore.length < 2 || questionCore.length < 2) return 0;
  if (queryCore === questionCore) return 1;

  const queryTerms = staticCommonQaMatchTerms(queryCore);
  const questionTerms = staticCommonQaMatchTerms(questionCore);
  const overlap = [...queryTerms].filter((term) => questionTerms.has(term)).length;
  if (overlap < 2) return 0;
  const keywordHits = (row?.keywords || []).filter((keyword) => {
    const normalized = staticCommonQaCoreText(keyword);
    return normalized.length >= 2 && queryCore.includes(normalized);
  }).length;
  if (!keywordHits && overlap < 3) return 0;
  const queryChars = new Set(queryCore);
  const questionChars = new Set(questionCore);
  const sharedChars = [...queryChars].filter((char) => questionChars.has(char)).length;
  const charDice = (2 * sharedChars) / Math.max(queryChars.size + questionChars.size, 1);
  const questionCoverage = overlap / Math.max(questionTerms.size, 1);
  const queryCoverage = overlap / Math.max(queryTerms.size, 1);
  const keywordScore = Math.min(1, keywordHits / Math.max(1, Math.min((row?.keywords || []).length, 2)));
  const score = questionCoverage * 0.38
    + queryCoverage * 0.18
    + charDice * 0.20
    + keywordScore * 0.16;
  const queryIntents = staticCommonQaIntents(query);
  const questionIntents = staticCommonQaIntents(row?.question);
  const sharedIntents = [...queryIntents].filter((intent) => questionIntents.has(intent));
  let adjustedScore = score;
  if (queryIntents.size && questionIntents.size) {
    adjustedScore = sharedIntents.length ? adjustedScore + 0.14 : adjustedScore * 0.35;
  } else if (queryIntents.size && !questionIntents.size) {
    adjustedScore *= 0.75;
  }
  const lengthRatio = Math.min(queryCore.length, questionCore.length) / Math.max(queryCore.length, questionCore.length, 1);
  if (queryCore.includes(questionCore) || questionCore.includes(queryCore)) {
    adjustedScore += lengthRatio >= 0.55 ? 0.06 * lengthRatio : -0.08;
  }
  return Math.min(adjustedScore, 0.99);
}

function matchStaticCommonQaCandidates(query, catalog = [], limit = 6) {
  const candidates = catalog.map((row) => ({ row, score: staticCommonQaScore(query, row) }))
    .filter((item) => item.row?.approved_answer && item.score >= 0.28)
    .sort((a, b) => b.score - a.score || Number(b.row.usage_count || 0) - Number(a.row.usage_count || 0) || String(b.row.question || "").length - String(a.row.question || "").length);
  return candidates.slice(0, limit).map((candidate) => ({
    ...candidate,
    score: Number(candidate.score.toFixed(3)),
    intent_match: [...staticCommonQaIntents(query)].some((intent) => staticCommonQaIntents(candidate.row.question).has(intent)),
  }));
}

function matchStaticCommonQa(query, catalog = []) {
  const best = matchStaticCommonQaCandidates(query, catalog, 6)[0];
  if (!best || best.score < 0.84) return null;
  const queryIntents = staticCommonQaIntents(query);
  const rowIntents = staticCommonQaIntents(best.row.question);
  if (queryIntents.size && rowIntents.size && ![...queryIntents].some((intent) => rowIntents.has(intent))) return null;
  return { ...best, query, candidate_count: 1, selection: "deterministic" };
}

function staticPointWaveBestCommonQa(query, catalog = []) {
  if (!isStaticPointWaveAftercareQuery(query)) return null;
  const row = catalog.find((item) => item?.id === "FAQ-XLS-0002");
  if (!row) return null;
  return {
    row,
    score: 1,
    query,
    candidate_count: 1,
    selection: "point_wave_best_answer",
    answer: staticPointWaveAftercareReply(query),
  };
}

function publicStaticCommonQaMatch(match) {
  const row = match?.row || {};
  return { id: row.id || "", question: row.question || "", score: match?.score || 0, status: row.status || "", candidate_count: match?.candidate_count || 1, selection: match?.selection || "candidate" };
}

const STATIC_FAQ_CUSTOMER_VOICE_LEAK = /知识库|当前课程|这个问题涉及|标准问答|方法路由|SOP|按流程|门店员工|员工应该|顾客应当|来源(?:资料|文件)|检索(?:资料|结果)/i;
const STATIC_QA_POLICY_VOICE_LEAK = /知识库|当前课程|这个问题涉及|标准问答|方法路由|SOP|按流程|门店员工|员工应该|顾客应当|来源(?:资料|文件)|检索(?:资料|结果)|不在门店|不能由门店|(?:门店|当前|本次).{0,18}(?:不能|不应|不建议|需要|必须|应当)|(?:项目|症状|异常).{0,16}(?:不能先|需要先|必须先|应当先|应先)/i;
// In ordinary customer-facing answers, a direct next step is clearer than
// corrective wording.  Safety, medical and prescription boundaries are
// deliberately exempted by the normalizers below.
const STATIC_UNNECESSARY_NEGATIVE_CUSTOMER_VOICE = /(?:不是|不能|不要|不应|不建议|不把.{0,16}(?:当作|说成|解释成)|无法|不可|不先|不急着|不直接|不替(?:您|你)?|不安排|不操作|不销售|不继续|不做|不承诺|不保证)/i;
const STATIC_QA_OFF_TOPIC_REPLY_PATTERN = /天气|吃饭|星座|新闻|周末去哪|电影|追剧|八卦/i;

function staticFaqCustomerVoiceFallback(match) {
  const row = match?.row || {};
  const question = String(row.question || match?.query || "").trim();
  const approvedAnswer = String(row.approved_answer || match?.answer || "").trim();
  // Keep the highest-volume point-wave “what is the principle?” FAQ useful
  // even without a model.  This is a customer-facing rendering of the
  // approved answer below, not a new claim: it retains the project type,
  // possible sensations, adjustable/pause boundary, observable scope, and
  // no-diagnosis/no-fixed-result limit.
  if (/点阵波/.test(question) && /原理|是什么|定位/.test(question)
    && /局部重复机械刺激/.test(approvedAnswer)) {
    return "我先直接回答您：点阵波是以局部重复机械刺激为主的体验项目，过程中可能感到敲击、振动或酸胀。开始前我会先了解体验部位和当前情况，从您能接受的程度开始；感受不舒服时可以随时调整或暂停。我们只观察当次体感和同一动作的变化，不把它当成医疗诊断或疾病治疗，也不承诺固定效果。";
  }
  // An accepted FAQ is already a bounded knowledge source.  In Pages/offline
  // mode we must not discard that answer simply because there is no model to
  // paraphrase it.  Only pass through a source answer when it is free of
  // internal workflow language and the same unsafe claims/actions rejected by
  // the normal QA path.
  if (approvedAnswer
    && approvedAnswer.length <= 700
    && !STATIC_FAQ_CUSTOMER_VOICE_LEAK.test(approvedAnswer)
    && !STATIC_QA_UNSAFE_ACTION_PATTERN.test(approvedAnswer)
    && !STATIC_QA_UNSUPPORTED_PRODUCT_CLAIM_PATTERN.test(approvedAnswer)) {
    return `我先直接回答您：${approvedAnswer}`;
  }
  if (question) return `您问的“${question}”，我先为您核对当前可以公开说明的内容。请告诉我现在最想了解的是感受、适用性还是服务后的变化，我会结合您当前情况按已核验的信息为您说明。`;
  return "我先为您核对当前可以公开说明的内容。请补充一下现在最想了解的项目和情况，我会结合您当前情况按已核验的信息为您说明。";
}

function staticFaqAnswerNeedsCustomerVoiceRepair(answer) {
  const text = String(answer || "").trim();
  return !text || STATIC_FAQ_CUSTOMER_VOICE_LEAK.test(text) || (text.length >= 36 && !/[我我们您你]/.test(text));
}

function staticQaCustomerVoiceFallback(message = "", query = "", route = {}) {
  const context = String(query || message || "").trim();
  const topics = staticDialogueTopicTags(message || context);
  if (staticPostServiceAdverseEvent(context)) {
    return STATIC_POST_SERVICE_ADVERSE_URGENT_PATTERN.test(normalizeStaticSafetyText(context))
      ? STATIC_POST_SERVICE_ADVERSE_URGENT_REPLY
      : STATIC_POST_SERVICE_ADVERSE_REPLY;
  }
  if (route?.intent_id === "INTENT-RED-FLAG" || route?.stop_sales) {
    if (/(?:现在|接下来).{0,10}(?:怎么办|做什么)|(?:怎么办|做什么)(?:呢)?[？?]?$/.test(String(message || ""))) {
      return "您现在先不要继续安排项目，也先不要自行处理；请尽快联系急救或前往医疗机构评估。为了方便您尽快获得帮助，我会把您刚才提到的症状和时间记录下来，并同步负责人跟进。";
    }
    return "我理解您现在会担心。为了您的安全，我现在不会为您安排项目，也不能通过聊天替您判断原因；麻烦您尽快联系急救或前往医疗机构评估。我会记录您刚才提到的时间和症状，并同步负责人跟进。";
  }
  if (/GLP-1|司美|减肥针|处方|药品|减肥药|口服片|剂量|停药|换药/i.test(context)) {
    return "我不能替您调整药物、剂量或停换药。麻烦您带上药品包装和用药记录，联系开药医生或药师核实；如果您现在有不适，也请一并说明。";
  }
  if (/孩子|儿童|未成年|孕妇|怀孕|备孕|哺乳|慢病|糖尿病|高血压|三高/i.test(context)) {
    return "我现在不能仅凭聊天替您确认是否适合安排项目或产品。麻烦您先告诉我具体阶段、健康和用药情况；我会协助您按产品或设备说明核对，并建议您由有资质的专业人员确认。";
  }
  if (/敏感肌|皮肤过敏|容易过敏|医美恢复|泛红|刺痛|破损/i.test(context)) {
    return "我先不急着替您判断能不能做。麻烦您告诉我现在有没有泛红、刺痛、破损、渗出或过敏发作，以及近期做过哪些项目、用了哪些产品；我会据此核对适用边界，情况不清楚时先不为您安排操作。";
  }
  if (/(?:背部|后背).{0,8}(?:凉|冷)|(?:凉|冷).{0,8}(?:背部|后背)|器官功能/i.test(context)) {
    return "我理解您担心这个感受。我不能仅凭背部发凉替您判断器官或疾病；麻烦您告诉我从什么时候开始、有没有持续或加重，以及是否伴疼痛、麻木、无力或其他不适。症状明显、持续或伴异常时，我建议您尽快到医疗机构评估。";
  }
  if (/水分测试笔|水分(?:测试|数值|值)|含水量|含水(?:测试|数值)/i.test(context)) {
    return "我可以先帮您把这次测量条件核对清楚。这次读数可以作为当次记录；请尽量使用同一设备、部位、时间和环境连续记录，并把护肤、清洁和测量时间一起告诉我，我会帮您一起看阶段变化。";
  }
  if (staticCurrentMessageRequestsDuration(message)) {
    return "您问的是需要多久。我会先确认您想了解的是一次体验大约需要多久，还是多久能观察到变化；请告诉我具体项目，我会按当前安排为您核对。";
  }
  if (route?.intent_id === "INTENT-PRICE") {
    return "我可以为您核对当前有效价格和权益。请告诉我城市、门店、具体项目和日期，我会按当前生效版本为您确认。";
  }
  if (topics.has("price")) {
    return "您问的是费用。我会按您咨询的城市、门店、具体项目和日期核对当前有效价格与活动；麻烦您把这几项告诉我，我马上为您查清楚。";
  }
  if (route?.intent_id === "INTENT-RESULT" || /一次|几次|多久|有效|见效|保证|反弹/i.test(context)) {
    return "我理解您希望尽快看到变化。我会先和您确认最想改善的具体指标和现在的情况，再用相同条件记录阶段变化；每个人的变化节奏会不同，我会按已核验的信息和您一起确定下一步。";
  }
  if (route?.intent_id === "INTENT-COMPARISON") {
    return "我可以围绕您想改善的问题、体验感受、时间和预算逐项比较。请告诉我正在比较的两个项目和最在意的一项标准，我会按已核验的信息为您说明。";
  }
  if (topics.has("comparison")) {
    return "您问的是项目之间的差别。请告诉我正在比较的两个项目，以及最在意感受、时间还是预算，我会按当前已核验的信息逐项为您说明。";
  }
  if (topics.has("time")) {
    return "您问的是需要多久。我会结合具体项目、您当前情况和服务安排为您核对可用时间；请先告诉我咨询的是哪一个项目。";
  }
  if (topics.has("measurement")) {
    return "您问的是测量结果。我会先把这次数据作为当次记录，再在同一设备、同一部位和相近时间下连续观察，和您一起看变化趋势。";
  }
  if (topics.has("privacy")) {
    return "我会先说明每项信息的用途，只了解与您当前咨询和服务安排直接相关的内容；您可以按自己的舒适度决定愿意提供哪些信息。";
  }
  if (staticQaCurrentIntent(message, query, route) === "definition") {
    return "我可以先为您说明这个项目的定位、体验和适用范围。请告诉我您想先了解原理、感受还是安排，我会按已核验的信息为您说明。";
  }
  if (staticQaCurrentIntent(message, query, route) === "process") {
    return "我可以按步骤为您说明服务安排、体验时间和需要确认的信息。请告诉我具体项目和最在意的环节，我会为您整理下一步。";
  }
  if (staticQaCurrentIntent(message, query, route) === "suitability") {
    return "我会先确认您当前状态、想改善的问题和近期相关情况，再按已核验的信息说明适用范围和下一步。";
  }
  return "我理解您在关心这个问题。我会先围绕您当前想了解的项目和情况整理已核验的信息；请告诉我具体项目、最想改善的地方和目前情况，我会为您说明下一步。";
}

function staticQaAnswerNeedsEmployeeVoiceRepair(answer) {
  const text = String(answer || "").trim();
  // A factual answer does not need to begin with “我/我们” to be something an
  // employee can say to a customer.  For example, “点阵波是以局部重复机械
  // 刺激为主的体验项目” is a direct answer; rejecting it merely because it
  // lacks a first-person pronoun made the UI replace it with the same generic
  // clarification template for otherwise well-grounded questions.
  //
  // Keep the real boundary here: empty output and leaked internal/process
  // language still require repair.  Relevance and unsupported-claim checks in
  // normalizeStaticQaResult continue to own the answer scope.
  return !text || STATIC_QA_POLICY_VOICE_LEAK.test(text);
}

// Keep the Pages build on the same compact current-turn vocabulary as the
// server.  These tags are intentionally customer-facing rather than a second
// retrieval system: they only block an answer that clearly drifted elsewhere.
const STATIC_DIALOGUE_TOPIC_PATTERNS = {
  price: /价格|多少钱|费用|太贵|预算|优惠|活动|便宜|贵在哪里/i,
  result: /效果|有没有用|有用吗|见效|改善|反弹|一次|几次|瘦|减重|体重|腰围|变化/i,
  time: /多久|多长时间|什么时候|何时|哪天|几天|几周|几个月|几年|时长|时间|持续|开始/i,
  pain_safety: /疼|痛|不舒服|不适|麻木|发麻|无力|红肿|发热|头晕|胸痛|胸闷|呼吸困难|晕厥|灼热|刺痛|电到|电击|加重|异常|过敏|破损|渗出/i,
  drug: /司美|利拉|贝那|GLP|减肥药|药品|用药|剂量|停药|换药|处方/i,
  privacy: /隐私|保密|不想说|不愿说|私人的|信息安全/i,
  comparison: /区别|差别|对比|比较|一样吗|哪个更/i,
  suitability: /适合|能做|可不可以做|敏感肌|孕|备孕|哺乳|儿童|未成年|慢病|高血压|糖尿病|植入物/i,
  service: /点阵波|超V|超声炮|冰雕|热玛吉|射频|水光|纳米喷射|磁波|智能提拉|头皮|项目|设备/i,
  location: /城市|门店|哪家店|哪个店|在哪里|地址/i,
  measurement: /测量|复测|记录|数据|同一条件|体脂/i,
};
const STATIC_DIALOGUE_STRONG_TOPIC_TAGS = new Set(Object.keys(STATIC_DIALOGUE_TOPIC_PATTERNS));

function staticCurrentMessageRequestsDuration(value = "") {
  const text = String(value || "").trim();
  return Boolean(text)
    && /多久|多长时间|多长(?:时|时间)|需要(?:多长)?时间|要(?:多长)?时间|时长/i.test(text)
    && !/价格|多少钱|收费|费用|预算|优惠|活动|贵|便宜/i.test(text);
}

function staticDialogueTopicTags(value = "") {
  const text = String(value || "").trim();
  return new Set(Object.entries(STATIC_DIALOGUE_TOPIC_PATTERNS)
    .filter(([, pattern]) => pattern.test(text))
    .map(([name]) => name));
}

function staticDialogueStrongTopics(value = "") {
  return new Set([...staticDialogueTopicTags(value)].filter((topic) => STATIC_DIALOGUE_STRONG_TOPIC_TAGS.has(topic)));
}

function staticLatestCustomerMessage(history = [], scenario = {}) {
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const item = history[index] || {};
    if (item.role !== "assistant") continue;
    const content = String(item.content || "").trim();
    if (content) return content;
  }
  return String(scenario?.opening || "").trim();
}

function staticDialogueHasExplicitSafetyBoundary(value = "", route = {}) {
  const text = normalizeStaticSafetyText(String(value || "").trim());
  if (route?.stop_sales || ["INTENT-RED-FLAG", "INTENT-DRUG"].includes(route?.intent_id)) return true;
  if (staticPostServiceAdverseEvent(text) || isStaticPointWaveAftercareQuery(text)) return true;
  return /胸痛|呼吸困难|晕厥|麻木|无力|发热|红肿|明显(?:疼|痛)|疼痛.{0,8}(?:加重|更)|处方|用药|剂量|停药|换药|诊断|疾病|孕妇|怀孕|备孕|哺乳|儿童|未成年|敏感肌|过敏|破损|渗出|医美恢复|植入物/i.test(text);
}

function staticQaCurrentIntent(message = "", query = "", route = {}) {
  const current = String(message || "").trim();
  const context = `${current} ${String(query || "").trim()}`;
  const intentId = String(route?.intent_id || "");
  if (staticCurrentMessageRequestsDuration(current)) return "result";
  if (intentId === "INTENT-PRICE" || /价格|多少钱|收费|费用|预算|优惠|活动|贵|便宜/i.test(context)) return "price";
  if (intentId === "INTENT-DRUG" || /GLP-1|司美|利拉|贝那|减肥针|减肥药|处方|药品|用药|剂量|停药|换药/i.test(context)) return "drug";
  if (intentId === "INTENT-RED-FLAG" || route?.stop_sales || /胸痛|胸闷|呼吸困难|晕厥|进行性麻木|无力|发热|红肿/i.test(context)) return "safety";
  if (intentId === "INTENT-RESULT" || /一次|几次|多久|有效|效果|见效|保证|反弹|改善/i.test(context)) return "result";
  if (intentId === "INTENT-COMPARISON" || /区别|比较|哪个.{0,8}(?:好|适合)|(?:和|与).{0,12}(?:区别|比较)/i.test(context)) return "comparison";
  if (/隐私|不想说|不愿回答|不想被问|个人信息/i.test(context)) return "privacy";
  if (/副作用|不良反应|反应|不适|疼痛|酸胀|刺痛|红肿|过敏|风险/i.test(context)) return "adverse";
  if (intentId === "INTENT-SUITABILITY" || /适合|能做|可以做|禁忌|肤况|皮肤状态|孕妇|哺乳|术后/i.test(context)) return "suitability";
  if (/什么是|是什么|原理|定位|怎么工作|作用是什么/i.test(context)) return "definition";
  if (/怎么做|如何做|流程|步骤|安排|部位|频率|次数/i.test(context)) return "process";
  return "general";
}

function staticQaAnswerIsRelevant(answer, message = "", query = "", route = {}) {
  const reply = String(answer || "").trim();
  if (!reply || STATIC_QA_OFF_TOPIC_REPLY_PATTERN.test(reply)) return false;
  const intent = staticQaCurrentIntent(message, query, route);
  const intentTerms = {
    price: /价格|费用|预算|贵|便宜|优惠|权益|城市|门店|项目|日期|核对/i,
    drug: /药|处方|医生|药师|剂量|包装|用药|记录|症状|核实/i,
    safety: /暂停|停止|记录|负责人|医疗|就医|急救|评估|症状|异常/i,
    result: /目标|指标|记录|复测|复盘|阶段|变化|时间|节奏|个体差异/i,
    comparison: /比较|区别|两个|标准|体验|时间|预算|项目|感受/i,
    privacy: /隐私|用途|必要信息|选择|同意|分享|说明/i,
    adverse: /反应|不适|症状|变化|感受|程度|时间|记录|联系|评估|风险|安全/i,
    suitability: /状态|肤况|皮肤|安全|限制|项目|确认|近期|适用|说明/i,
    definition: /项目|服务|设备|原理|定位|体验|作用|方式|特点/i,
    process: /流程|步骤|安排|时间|部位|频率|次数|体验|确认/i,
  };
  if (intentTerms[intent]) return intentTerms[intent].test(reply);

  const ignoredTerms = new Set(["请问", "问一", "一下", "什么", "么是", "怎么", "如何", "可以", "能不", "不能", "是否", "现在", "目前", "这个", "那个", "问题", "情况", "服务", "顾客", "我们", "你们", "了解"]);
  const questionTerms = [...staticCommonQaMatchTerms(String(message || query || ""))]
    .filter((term) => term.length >= 2 && !ignoredTerms.has(term));
  const answerTerms = staticCommonQaMatchTerms(reply);
  if (questionTerms.some((term) => answerTerms.has(term))) return true;
  return /(?:我会|我先|我们先|请告诉我|麻烦您).{0,48}(?:具体项目|最想改善|当前情况|当前状态|想了解|最在意)/i.test(reply);
}

function staticQaAnswerIsCurrentTurnRelevant(answer, currentMessage = "", contextualQuery = "", route = {}) {
  const reply = String(answer || "").trim();
  const current = String(currentMessage || "").trim();
  const context = String(contextualQuery || "").trim();
  if (!reply) return false;
  if (staticDialogueHasExplicitSafetyBoundary(current || context, route)) return true;
  const shortReference = current.length <= 36
    && /^(?:那|这个|这种|它|刚才|为什么|多少钱|多少|多久|怎么办|可以吗)/i.test(current);
  const currentTopics = staticDialogueStrongTopics(current);
  const contextTopics = staticDialogueStrongTopics(context);
  let focus;
  // A short follow-up can inherit the project identity, but an explicit new
  // predicate such as “那要多久？” must not accept an answer to the earlier
  // price/effect question merely because it appears in the context.
  if (shortReference && currentTopics.size) {
    // The inherited service gives the model context, but does not itself make
    // a response relevant.  “那要多久？” must receive a time answer even
    // when its preceding turn was about a project's price.
    focus = new Set(currentTopics);
  } else {
    focus = shortReference ? contextTopics : currentTopics;
  }
  const answerTopics = staticDialogueStrongTopics(reply);
  if (!focus.size || !answerTopics.size) return true;
  return [...focus].some((topic) => answerTopics.has(topic));
}

function staticQaNeedsPositiveCustomerVoiceRepair(answer, message = "", query = "", route = {}, policyOwnedAction = false) {
  const context = String(query || message || "");
  if (policyOwnedAction || staticDialogueHasExplicitSafetyBoundary(context, route)) return false;
  return STATIC_UNNECESSARY_NEGATIVE_CUSTOMER_VOICE.test(String(answer || ""));
}

function staticCommonQaDocument(match) {
  const row = match?.row || {};
  return {
    document_id: row.id || "",
    text: String(row.approved_answer || ""),
    metadata: {
      doc_type: "common_qa",
      title: row.question || "顾客常见问题",
      course_id: staticCommonQaCourseIds(row)[0] || "",
      domain: row.domain || "",
    },
  };
}

function staticCommonQaCourseReference(row) {
  const course = resolveReferenceCourse({ course_id: staticCommonQaCourseIds(row)[0] });
  if (!course) return null;
  const module = moduleById(course.module_id);
  return {
    course_id: course.id,
    title: course.title,
    category: "标准问答课程",
    module: module?.short_name || module?.title || "知识模块",
    chapter: course.group_title || "",
  };
}

function uniqueStaticReferences(references = []) {
  const seen = new Set();
  return references.filter((reference) => {
    const key = reference.course_id || reference.title;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

const COMMON_QA_LEGACY_COURSE_IDS = {
  "COURSE-FAQ-POINT-WAVE-001": ["COURSE-NKB-010", "COURSE-NKB-011", "COURSE-NKB-012"],
  "COURSE-FAQ-SUPER-V-001": ["COURSE-NKB-017", "COURSE-NKB-018", "COURSE-NKB-019"],
  "COURSE-FAQ-SLIMMING-001": ["COURSE-NKB-020", "COURSE-NKB-021", "COURSE-NKB-022", "COURSE-NKB-023"],
  "COURSE-FAQ-OBJECTION-001": ["COURSE-NKB-007", "COURSE-NKB-008"],
  "COURSE-FAQ-SAFETY-001": ["COURSE-NKB-003"],
  "COURSE-FAQ-BEAUTY-001": ["COURSE-NKB-033", "COURSE-NKB-036", "COURSE-NKB-038", "COURSE-NKB-039", "COURSE-NKB-040", "COURSE-NKB-043"],
};

function staticCommonQaCourseIds(row = {}) {
  const requestedId = String(row.mapped_course_id || "");
  if (state.courses.some((course) => course.id === requestedId)) return [requestedId];
  let candidates = [...(COMMON_QA_LEGACY_COURSE_IDS[requestedId] || [])];
  const question = `${row.question || ""} ${(row.keywords || []).join(" ")}`;
  const intents = staticCommonQaIntents(question);
  if (requestedId === "COURSE-FAQ-POINT-WAVE-001") {
    if (intents.has("adverse_effect")) candidates = ["COURSE-NKB-012", "COURSE-NKB-015", ...candidates];
    else if (intents.has("comparison")) candidates = ["COURSE-NKB-013", ...candidates];
    else if (intents.has("suitability")) candidates = ["COURSE-NKB-016", "COURSE-NKB-003", ...candidates];
    else if (intents.has("process")) candidates = ["COURSE-NKB-011", ...candidates];
    else if (intents.has("definition")) candidates = ["COURSE-NKB-010", ...candidates];
  } else if (requestedId === "COURSE-FAQ-SUPER-V-001") {
    candidates = intents.has("adverse_effect") ? ["COURSE-NKB-018", ...candidates] : ["COURSE-NKB-017", ...candidates];
  } else if (requestedId === "COURSE-FAQ-SLIMMING-001") {
    if (intents.has("adverse_effect")) candidates = ["COURSE-NKB-024", "COURSE-NKB-027", ...candidates];
    else if (intents.has("suitability")) candidates = ["COURSE-NKB-025", ...candidates];
    else candidates = ["COURSE-NKB-020", "COURSE-NKB-021", ...candidates];
  } else if (requestedId === "COURSE-FAQ-OBJECTION-001") candidates = ["COURSE-NKB-008", ...candidates];
  else if (requestedId === "COURSE-FAQ-SAFETY-001") candidates = ["COURSE-NKB-003", ...candidates];
  return uniqueStaticItems(candidates).filter((id) => state.courses.some((course) => course.id === id));
}

function staticPreferredCourseIds(query) {
  const text = String(query || "").replaceAll("点振波", "点阵波");
  const intents = staticCommonQaIntents(text);
  if (/点阵波|点振波/i.test(text)) {
    if (intents.has("adverse_effect")) return ["COURSE-NKB-012"];
    if (intents.has("comparison")) return ["COURSE-NKB-013"];
    if (/超V|热动力|联合/i.test(text)) return ["COURSE-NKB-014"];
    if (intents.has("suitability")) return ["COURSE-NKB-016", "COURSE-NKB-003"];
    if (intents.has("process")) return ["COURSE-NKB-011"];
    if (intents.has("definition")) return ["COURSE-NKB-010"];
    return ["COURSE-NKB-010", "COURSE-NKB-011"];
  }
  if (/超V|热动力/i.test(text)) return intents.has("adverse_effect") ? ["COURSE-NKB-018", "COURSE-NKB-019"] : ["COURSE-NKB-017", "COURSE-NKB-018"];
  if (/减肥|减重|体重|贝那鲁肽|GLP.?1|美妥/i.test(text)) {
    if (intents.has("adverse_effect")) return ["COURSE-NKB-024", "COURSE-NKB-027"];
    if (intents.has("suitability")) return ["COURSE-NKB-025", "COURSE-NKB-027"];
    return ["COURSE-NKB-020", "COURSE-NKB-021", "COURSE-NKB-022"];
  }
  if (/脱毛|祛斑|水光|皮肤|敏感肌|线雕|热玛吉|玻尿酸|私密/i.test(text)) {
    if (/脱毛/i.test(text)) return ["COURSE-NKB-036"];
    return ["COURSE-NKB-033", "COURSE-NKB-038", "COURSE-NKB-040", "COURSE-NKB-043"];
  }
  return [];
}

function staticRetrieve(query, documents, limit = 8, route = null, includeCommonQa = true) {
  const text = String(query || "").replaceAll("点振波", "点阵波").toLowerCase();
  const stopTerms = new Set(["这个", "那个", "这些", "那些", "项目", "服务", "可以", "不能", "能不", "是不是", "是否", "怎么", "如何", "什么", "有没有", "请问", "我想", "你们", "我们", "现在", "一下", "一个", "哪些", "有哪", "吗", "呢", "一次", "几次", "需要"]);
  const terms = new Set(text.match(/[a-z0-9_]{2,}/gi) || []);
  (text.match(/[\u4e00-\u9fff]+/g) || []).forEach((segment) => {
    if (segment.length <= 8) terms.add(segment);
    for (let index = 0; index < segment.length - 1; index += 1) terms.add(segment.slice(index, index + 2));
  });
  const requiredCourseIds = new Set(route?.required_course_ids || []);
  const routedModuleIds = new Set([route?.primary_module_id, ...(route?.support_module_ids || [])].filter(Boolean));
  const preferredCourseIds = new Set(staticPreferredCourseIds(query));
  const ranked = documents.map((document, index) => {
    const metadata = document.metadata || {};
    if (metadata.doc_type === "source") return null;
    if (!includeCommonQa && metadata.doc_type === "common_qa") return null;
    if (route && metadata.doc_type === "course_section" && !routedModuleIds.has(metadata.module_id) && !requiredCourseIds.has(metadata.course_id)) return null;
    if (preferredCourseIds.size && ["course_section", "integrated_course_section"].includes(metadata.doc_type) && !preferredCourseIds.has(metadata.course_id)) return null;
    const title = String(metadata.title || "").toLowerCase();
    const haystack = `${document.text || ""} ${JSON.stringify(metadata)}`.toLowerCase();
    const baseScore = [...terms].reduce((total, term) => total + (title.includes(term) ? 4 : haystack.includes(term) ? 1 : 0), 0);
    const routeBonus = (requiredCourseIds.has(metadata.course_id) ? 10 : 0) + (routedModuleIds.has(metadata.module_id) ? 3 : 0);
    const score = baseScore + routeBonus;
    if (baseScore <= 0 && ["course_section", "integrated_course_section"].includes(metadata.doc_type)) return null;
    return { document, score, index };
  }).filter((item) => item && item.score > 0).sort((a, b) => b.score - a.score || a.index - b.index);
  const selected = [];
  const seen = new Set();
  for (const courseId of requiredCourseIds) {
    const item = ranked.find((candidate) => candidate.document.metadata?.course_id === courseId);
    if (!item) continue;
    selected.push(item.document);
    seen.add(courseId);
    if (selected.length >= limit) return selected;
  }
  for (const item of ranked) {
    const metadata = item.document.metadata || {};
    const key = metadata.course_id || metadata.source_id || item.document.document_id;
    if (seen.has(key)) continue;
    seen.add(key);
    selected.push(item.document);
    if (selected.length >= limit) break;
  }
  return selected;
}

function extractStaticJson(content) {
  const cleaned = String(content || "").replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    const match = cleaned.match(/\{[\s\S]*\}/);
    try { return match ? JSON.parse(match[0]) : null; } catch { return null; }
  }
}

async function callStaticModel(system, messages, model, apiKey, temperature, maxTokens = 1800, timeoutMs = 45000) {
  const payload = {
    model, messages: [{ role: "system", content: system }, ...messages],
    temperature, top_p: 0.7, max_tokens: maxTokens, response_format: { type: "json_object" }, stream: false,
  };
  if (model.startsWith("Qwen/Qwen3") || model.includes("DeepSeek-V3.2") || model.startsWith("Pro/zai-org/GLM-5")) payload.enable_thinking = false;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch("https://api.siliconflow.cn/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(`SiliconFlow API ${response.status}: ${data.error?.message || "请求失败"}`);
    return { content: data.choices?.[0]?.message?.content || "", meta: { model: data.model || model, usage: data.usage || {} } };
  } catch (error) {
    if (controller.signal.aborted) throw new Error("在线 AI 响应超时，请稍后重试。");
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

const STATIC_COMMON_QA_JUDGE_SYSTEM = `你是常见问答的严格路由判断器。你的任务不是凭空回答，而是判断当前顾客问题是否被候选标准问答真正覆盖。
必须遵守：
1. 先比较当前问题与每个候选问题的核心意图。项目相同不代表问题相同；“是什么/原理”“副作用/不适”“能不能做/风险”“效果/多久”“价格”“区别”不能互相替代。
2. 只有候选问题和标准答案能够直接回答当前问题时才选择；如果候选只能回答项目背景、但当前问的是副作用或风险，必须返回 NONE。
3. 选择后只能基于被选候选的 approved_answer 做压缩、分点或口语化整理，不得增加候选答案没有的事实、承诺、治疗结论、用法或数字。
4. 不要把候选问题拼接成一个新答案。无法确认时宁可 NONE，系统会回退到知识库检索。
严格输出 JSON：{"match_id":"候选id或NONE","confidence":0.0,"answer":"整理后的直接回答；NONE时为空","reason":"一句话说明意图是否一致"}`;

function staticCommonQaAnswerGrounded(answer, approvedAnswer) {
  const text = String(answer || "").trim();
  const approved = String(approvedAnswer || "").trim();
  if (!text || text.length > 700 || /保证|一定|治愈|根治|固定减重|药品剂量|停药/i.test(text)) return false;
  const answerTerms = staticCommonQaMatchTerms(text);
  const approvedTerms = staticCommonQaMatchTerms(approved);
  return [...answerTerms].filter((term) => approvedTerms.has(term)).length >= 2;
}

async function selectStaticCommonQaWithModel(query, candidates, model, apiKey) {
  if (!candidates.length) return { match: null, meta: { attempted: false, candidate_count: 0 } };
  if (!apiKey) {
    const best = candidates[0];
    const queryIntents = staticCommonQaIntents(query);
    const rowIntents = staticCommonQaIntents(best.row.question);
    const accepted = best.score >= 0.84 && (!queryIntents.size || !rowIntents.size || [...queryIntents].some((intent) => rowIntents.has(intent)));
    return {
      match: accepted ? { ...best, query, candidate_count: candidates.length, selection: "deterministic" } : null,
      meta: { attempted: false, candidate_count: candidates.length, selection: accepted ? "deterministic" : "fallback_knowledge" },
    };
  }
  const prompt = JSON.stringify({
    current_question: query,
    candidates: candidates.map((candidate) => ({
      id: candidate.row.id,
      question: candidate.row.question,
      approved_answer: candidate.row.approved_answer,
      keywords: candidate.row.keywords || [],
      match_score: candidate.score,
    })),
  });
  let modelResult;
  try {
    modelResult = await callStaticModel(STATIC_COMMON_QA_JUDGE_SYSTEM, [{ role: "user", content: prompt }], model, apiKey, 0, 1000, 30000);
  } catch (error) {
    return { match: null, meta: { attempted: true, candidate_count: candidates.length, selection: "fallback_knowledge", error: String(error.message || error).slice(0, 160) } };
  }
  const payload = extractStaticJson(modelResult.content) || {};
  const matchId = String(payload.match_id || "").trim();
  const confidence = Number(payload.confidence || 0);
  const selected = candidates.find((candidate) => candidate.row.id === matchId);
  if (!selected || confidence < 0.62) return { match: null, meta: { ...modelResult.meta, attempted: true, candidate_count: candidates.length, selection: "fallback_knowledge" } };
  const organizedAnswer = String(payload.answer || "").trim();
  return {
    match: {
      ...selected,
      query,
      candidate_count: candidates.length,
      selection: "model_judged",
      model_confidence: Number(confidence.toFixed(3)),
      ...(staticCommonQaAnswerGrounded(organizedAnswer, selected.row.approved_answer) ? { answer: organizedAnswer } : {}),
    },
    meta: { ...modelResult.meta, attempted: true, candidate_count: candidates.length, selection: "model_judged" },
  };
}

function staticMock(mode, action, scenario) {
  if (mode === "training") return {
    customer_reply: staticCustomerFallback(scenario, [], ""),
    feedback: { level: "needs_work", issue: "还可以继续追问顾客的目标、持续时间和影响。", why: "先围绕顾客当前目标完成问题定位，再按已知信息说明下一步。", method_step: "了解目标并完成问题定位", knowledge_focus: "目标、持续时间、影响和安全信息", suggested_reply: "这种情况大概持续多久了？对工作或睡眠有影响吗？", next_goal: "下一轮先问清目标、持续时间和影响。" },
  };
  if (mode === "test" && action === "turn") return { reply: scenario?.opening || "我最近有点困扰，想先了解一下你们的项目。", emotion: "hesitant", should_continue: true };
  if (mode === "test" && action === "finish") return { total_score: 72, dimension_scores: [], critical_failures: [], strengths: ["完成了基本接待并保持对话连续"], improvements: ["先问清目标、持续时间、影响和顾虑，再介绍项目"], summary: "演示评分：流程已走通，配置 API Key 后可使用模型评分。" };
  return { answer: "当前是演示模式。保存 SiliconFlow API Key 后，就能生成基于知识库的正式回答。", uncertainties: ["请以门店当前价格、项目标签和合规版本为准。"], recommended_action: "先核对门店当前版本的价格、频次和适用边界。" };
}

function staticKnowledgeQaResponse(message, route, docs) {
  if (/(?:背部|后背).{0,8}(?:凉|冷)|(?:凉|冷).{0,8}(?:背部|后背)|器官功能/i.test(message)) {
    return {
      answer: "背部发凉是一种主观感受，不能据此判断某个器官功能不好，也不能由门店作疾病诊断。先确认持续时间、变化和伴随症状；症状明显、持续或伴随异常时应由医疗机构评估。",
      uncertainties: ["需要确认持续时间、变化、诱因和伴随症状。"],
      recommended_action: "先做风险问询；不能用项目体验替代医疗诊断或评估。",
    };
  }
  if (/水分测试笔|水分(?:测试|数值|值)|含水量|含水(?:测试|数值)/i.test(message)) {
    return {
      answer: "一次水分数值升高最多说明当次、当时测量出现变化，不能直接证明长期改善。比较时要使用同一设备、同一部位、相近时间和环境，并在相同条件下多次复测。",
      uncertainties: ["需要确认设备、部位、时间、环境和前后测量条件是否一致。"],
      recommended_action: "按统一条件记录并复测，不把单次读数宣传为长期效果。",
    };
  }
  if (route?.intent_id === "INTENT-RESULT" || /一次|几次|多久|有效|见效|保证|反弹/i.test(message)) {
    return {
      answer: "我理解您希望尽快看到变化，但不能承诺一次、固定时间或固定结果，也不能保证不反弹。先确认您最想改善的指标和既往情况，再按相同条件记录并做阶段观察；长期变化还会受到生活方式和个体差异影响。",
      uncertainties: ["需要确认具体项目、顾客目标和用于判断变化的指标。"],
      recommended_action: "先确定一个可观察指标和必要安全信息，再决定是否体验及何时复盘。",
    };
  }
  if (route?.intent_id === "INTENT-COMPARISON") {
    return {
      answer: "不同项目不能只按名称判断谁更好，需要围绕您想改善的问题、可接受的体验、时间安排和必要安全信息来比较。请先告诉我您正在比较哪两个项目，以及最在意效果感受、时间还是预算中的哪一点。",
      uncertainties: ["需要确认正在比较的具体项目和最重要的选择标准。"],
      recommended_action: "先补齐比较对象和选择标准，再按当前课程与门店有效版本逐项说明。",
    };
  }
  if ((route?.primary_module_id || "") === "MOD-05") {
    return {
      answer: "体重管理不能只凭一个数字直接推荐方案，也不能承诺固定减重斤数。先了解当前体重趋势、饮食、活动、睡眠、既往经历和健康情况，再把目标拆成可观察、能执行的阶段指标。",
      uncertainties: ["需要确认当前体重趋势、生活节奏、既往经历和必要健康信息。"],
      recommended_action: "先完成需求与风险问询，再确定一到两个阶段指标。",
    };
  }
  if ((route?.primary_module_id || "") === "MOD-04") {
    return {
      answer: "是否适合不能只凭一个肤质标签判断。先确认当前是否有泛红、刺痛、破损、渗出或过敏发作，以及近期是否做过医美、刷酸、激光或使用强刺激产品；无法确认时先不操作。",
      uncertainties: ["需要确认当前皮肤状态、过敏史、近期项目史和具体成分。"],
      recommended_action: "先完成肤况和项目适用性确认，再说明可选服务。",
    };
  }
  const snippets = [];
  const seenTitles = new Set();
  docs.slice(0, 2).forEach((document) => {
    const course = resolveReferenceCourse(document);
    const title = course?.title || document.metadata?.title || document.document_id || "知识库资料";
    if (seenTitles.has(title)) return;
    seenTitles.add(title);
    const section = course?.sections?.[0];
    const content = Array.isArray(section?.content)
      ? section.content.slice(0, 2).join("；")
      : typeof section?.content === "object" && section?.content
        ? Object.entries(section.content).map(([key, value]) => `${key}：${value}`).join("；")
        : String(section?.content || document.text || "");
    const snippet = `${course?.summary || ""} ${content}`.replace(/\s+/g, " ").trim();
    if (snippet) snippets.push(snippet.slice(0, 220));
  });
  if (!snippets.length) return staticMock("qa", "turn", null);
  return {
    answer: `围绕您问的“${String(message || "").trim()}”，知识库相关课程提到：${snippets.slice(0, 2).join("；")}`,
    uncertainties: ["具体项目、适用条件和门店动态政策仍需按当前有效版本核对。"],
    recommended_action: route.recommended_next || "如需继续了解，可打开下方相关课程并核对当前门店标准。",
  };
}

const STATIC_CRITICAL_PATTERNS = [
  /自动诊疗/i,
  /(?<!不)(?<!非)(?:是|属于|就是|诊断为).{0,8}(?:颈椎病|腰椎病|糖尿病|三高|脂肪肝|炎症|神经损伤|疾病)/i,
  /替代手术/i,
  /保证(?:效果|结果|瘦|减重)/i,
  /(?:保证|一定|肯定).{0,10}(?:治好|治愈|根治)/i,
  /(?:治愈|根治|治疗|治好)[^，。；！？,.;!?\r\n]{0,8}(?:疾病|颈椎病|糖尿病|三高|脂肪肝|炎症)/i,
  /(?:有效|能够|可以|会)[^，。；！？,.;!?\r\n]{0,10}(?:治疗|治好|根治|改善糖尿病|改善三高|改善脂肪肝|提高免疫力|增强免疫力)/i,
  /(?:固定|保证).{0,8}(?:减重|减肥).{0,8}(?:斤|公斤)/i,
  /不反弹/i,
  /百分之百|百分百|100%/i,
  /白血球.{0,10}(?:增加|提高)/i,
  /(?:宫寒|卵巢|肾虚).{0,12}(?:受孕|衰老|疾病|治疗)/i,
  /国家药监局.{0,20}(?:批准|认证)/i,
  /单次治疗|后续疗程|按疗程|进入疗程/i,
  /压迫.{0,8}(?:血管|神经)/i,
  /(?:可能)?涉及.{0,6}(?:神经|血管)/i,
  /脑部.{0,8}供血|供血供氧.{0,8}不足/i,
  /(?:检查|查体).{0,12}(?:僵硬程度|结节|体征)/i,
  /(?:一定|肯定|保证).{0,8}(?:有效|缓解|改善|见效|结果)/i,
  /(?:建议|应该|可以).{0,12}(?:停药|换药|改药|剂量|口服|注射|服用|吃.{0,4}(?:片|粒|药))/i,
  /(?:把|将)?.{0,12}(?:司美格鲁肽|利拉鲁肽|贝那鲁肽|减肥药|处方药|用药).{0,8}(?:停了|停掉|换掉|换成)/i,
  /(?:改成|改为|调整为|加到|减到).{0,12}(?:每天|每日|早晚|每次|\d+\s*(?:片|粒|次|毫克|mg))/i,
  /(?:回去|回家后?)?.{0,5}(?:吃|服用|口服).{0,8}(?:布洛芬|双氯芬酸|对乙酰氨基酚|阿司匹林|止痛药|消炎药)/i,
];

function staticCriticalHits(message) {
  const text = String(message || "");
  return STATIC_CRITICAL_PATTERNS
    .filter((pattern) => staticHasAffirmativeEmployeeMatch(text, pattern))
    .map((pattern) => pattern.source);
}

function staticMockProgressive(mode, action, scenario, history = [], rubric = null, message = "") {
  const userTurns = history.filter((item) => item?.role === "user").length;
  if (mode === "training") {
    const strong = ["了解", "多久", "哪里", "感受", "目标", "担心", "方便", "预算", "疼", "病史"].some((word) => String(message).includes(word));
    const critical = staticCriticalHits(message).length > 0;
    return {
      customer_reply: staticCustomerFallback(scenario, history, message, true),
      feedback: {
        level: critical ? "critical" : (strong ? "good" : "needs_work"),
        issue: critical ? "出现了不能承诺疗效或替代专业评估的高风险表达。" : (strong ? "你已围绕顾客的目标和情况继续追问，方向正确。" : "还可以继续追问顾客的目标、持续时间和影响。"),
        why: critical ? "安全边界优先，不能用确定性承诺或医疗化表达推进成交。" : "先围绕顾客当前目标完成问题定位，再按已知信息说明下一步。",
        method_step: "了解目标并完成问题定位",
        knowledge_focus: "目标、持续时间、影响和安全信息",
        suggested_reply: critical ? "我不能承诺结果或替代专业评估，先确认您的具体情况和安全边界，再说明可以提供的服务。" : "这种情况大概持续多久了？对工作或睡眠有影响吗？",
        next_goal: critical ? "下一轮先纠正表达，完成必要安全问询。" : "下一轮先问清目标、持续时间和影响。",
      },
    };
  }
  if (mode === "test" && action === "turn") {
    return { reply: staticCustomerFallback(scenario, history, message, true), emotion: userTurns > 0 ? "concerned" : "hesitant", should_continue: true };
  }
  if (mode === "test" && action === "finish") {
    const dimensions = (rubric?.dimensions || []).map((item) => ({
      id: item.id,
      name: item.name,
      score: Math.round(Number(item.weight || item.max_score || 0) * 0.72),
      max_score: Number(item.weight || item.max_score || 0),
      evidence: "本地演示评分：已根据当前对话完成基础评估。",
      comment: "建议继续训练需求分析和异议处理。",
    }));
    return { total_score: 72, dimension_scores: dimensions, critical_failures: [], strengths: ["完成了基本接待并保持了对话连续性。"], improvements: ["先问清目标、持续时间、影响和顾虑，再介绍项目。", "面对价格和效果异议时，使用共情—澄清—回应—确认。"], summary: "本地演示评分：流程已走通，配置 API Key 后可使用模型评分。" };
  }
  return staticMock(mode, action, scenario);
}

const STATIC_QA_INTERNAL_ACTION_PATTERN = /调用.{0,8}(?:QA|答案|课程)|具体QA|对应答案|知识库|方法路由|检索.{0,12}(?:标准问答|问答条目|课程|资料)|引用.{0,12}(?:标准问答|问答条目|课程)|document_id|source_id|CHUNK|INTENT-|MOD-|COURSE-/i;
const STATIC_QA_UNSAFE_ACTION_PATTERN = /(?:把|将)?.{0,12}(?:司美格鲁肽|利拉鲁肽|贝那鲁肽|减肥药|处方药|用药).{0,8}(?:停了|停掉|换掉|换成)|(?:改成|改为|调整为|加到|减到).{0,12}(?:每天|每日|早晚|每次|\d+\s*(?:片|粒|次|毫克|mg))|(?:吃|服用|口服).{0,8}(?:布洛芬|双氯芬酸|对乙酰氨基酚|阿司匹林|止痛药|消炎药)/i;
const STATIC_QA_UNSUPPORTED_PRODUCT_CLAIM_PATTERN = /(?:最|特别|非常|一定|肯定).{0,8}适合|(?:永久|永远).{0,14}(?:消除|减少|提拉|紧致|改善|瘦|去除|消失)|(?:消除|溶解|排出|冻掉).{0,14}(?:内脏脂肪|脂肪细胞)|(?:三天|一周|两周|\d+\s*(?:天|周|个月)).{0,12}(?:见效|恢复|消肿|消退|出效果|有效果)|(?:每周|每月|每天|每日|隔天).{0,12}(?:\d+|一|两|二|三|四|五|六|七|八|九|十)\s*次|(?:建议|直接|安排|需要).{0,18}(?:做|体验|服务|项目).{0,12}(?:\d+|一|两|二|三|四|五|六|七|八|九|十)\s*(?:次|疗程)/i;

function staticPublicRecommendedAction(route = {}) {
  if (route.intent_id === "INTENT-PRICE") return "确认城市、门店、具体项目和日期后，核对当前有效价格与权益。";
  if (route.intent_id === "INTENT-RESULT") return "先确认您最想改善的一个指标，再约定统一记录方式和阶段复盘时间。";
  if (route.intent_id === "INTENT-SUITABILITY") {
    if (route.primary_module_id === "MOD-05") return "先确认想改善的指标、当前趋势和必要安全信息，再说明阶段目标。";
    if (route.primary_module_id === "MOD-07") return "先确认想改善的部位、局部皮肤和近期项目，再核对塑形项目边界。";
    if (route.primary_module_id === "MOD-08") return "先确认当前皮肤状态、近期项目和必要安全信息，再核对具体项目说明。";
    if (route.primary_module_id === "MOD-09") return "先确认具体医美项目、近期治疗史、植入物和当前状态，再由有资质人员核对。";
    if (route.primary_module_id === "MOD-10") return "先保护隐私并确认顾客主动提出的目标、当前症状和必要安全信息。";
    return "先确认当前状态、想改善的问题和必要安全信息，再说明体验边界。";
  }
  if (route.intent_id === "INTENT-COMPARISON") return "请说明正在比较的两个项目和最在意的一项标准，再按可核验信息逐项说明。";
  if (route.intent_id === "INTENT-DECISION") return "先确认影响决定的主要顾虑，再给出继续了解、调整安排或暂不决定的选择。";
  const moduleActions = {
    "MOD-03": "先确认顾客最关心的是体验原理、服务部位还是当前不适，再按对应课程说明边界。",
    "MOD-04": "先确认顾客最关心的具体项目、当前肤况和近期项目，再按已核验资料说明体验边界。",
    "MOD-05": "先确认想改善的具体指标、当前趋势和必要安全信息，再说明可观察的下一步。",
    "MOD-07": "先确认想改善的具体部位、近期同部位项目和局部皮肤状态，再按当前标准说明塑形项目边界。",
    "MOD-08": "先确认具体设备或护理项目、当前皮肤状态和近期项目，再按已核验资料说明边界。",
    "MOD-09": "先确认具体医美项目、近期治疗史和当前状态；涉及医疗决定时由有资质人员核实。",
    "MOD-10": "先保护隐私并确认顾客主动提出的目标、当前状态和必要安全信息。",
  };
  if (moduleActions[route.primary_module_id]) return moduleActions[route.primary_module_id];
  return "先确认您当前最想了解的问题和一项必要信息，再按已核验标准说明可执行的下一步。";
}

function staticAffirmativeChildContext(value = "") {
  const text = String(value || "").replace(
    /(?:我|本人)?(?:并)?(?:不是|非|不属于)(?:儿童|未成年人?|少年|小孩子?)|不是给(?:孩子|儿童|未成年人?|小孩子?)(?:用|吃|问)?/gi,
    " ",
  );
  return /孩子|儿童|未成年人?|少年|小孩子?|儿子|女儿/i.test(text);
}

function normalizeStaticQaResult(result, message, query, route, history = []) {
  const normalized = result && typeof result === "object" ? { ...result } : {};
  const current = String(message || "").trim();
  const context = String(query || current);
  // The caller sets this only after selecting an approved FAQ answer locally.
  // It may retain a necessary factual boundary such as “不能宣称治疗疾病”,
  // which should not be replaced by the generic positive-language template.
  const controlledFaqAnswer = normalized.faq_controlled_answer === true;
  delete normalized.faq_controlled_answer;
  let policyOwnedAction = false;
  const followUp = /怎么办|现在|下一步|那我|接下来/.test(current) && history.some((item) => item?.role === "user");
  if (/(?:手麻|麻木).{0,18}(?:未缓解|没有缓解|加重)|(?:疼痛加重).{0,18}(?:麻木|手麻)/.test(context)) {
    normalized.answer = "您提到点阵波后疼痛加重并伴有手麻、且目前没有缓解，这需要优先由有资质的医疗人员评估。门店不能判断原因，也不能指导您在家采用热敷、冷敷或其他处理方式；在情况明确前，请停止项目和自行处理。";
    normalized.uncertainties = ["需要由医疗人员评估症状及是否存在紧急情况。"];
    normalized.recommended_action = "如症状持续、加重或伴随无力、胸痛、呼吸困难、晕厥等情况，请及时就医或联系急救；同时保留服务时间和反应记录。";
    policyOwnedAction = true;
  } else if (route.intent_id === "INTENT-RED-FLAG") {
    const affirmedContext = staticAffirmedSafetyText(context);
    const urgent = /胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|出冷汗|突发剧痛|突然剧痛|进行性麻木|麻木加重|持续麻木|(?:手|腿|胳膊).{0,4}麻|无力|大小便异常|会阴麻木|发热.{0,6}红肿|红肿.{0,6}发热|不能负重/i.test(affirmedContext);
    const diagnosed = /替代手术|已确诊|诊断为|腰椎间盘突出|颈椎病/i.test(affirmedContext);
    if (urgent) {
      normalized.answer = followUp
        ? "现在不要继续任何项目，也不要自行处理。若这些异常正在发生、持续或加重，请立即联系急救或尽快前往医疗机构；同时请身边人员陪同，并让门店负责人记录时间、变化和已采取的措施。"
        : "对话中已经出现需要优先处理的异常。现在先停止项目、销售沟通和自行处理，不在门店判断原因；请尽快联系急救或前往医疗机构评估，并由门店负责人记录服务时间、变化和已采取的措施。";
      normalized.uncertainties = ["需要确认症状是否正在发生、是否持续或加重，以及当前所在位置和可获得的帮助。"];
      normalized.recommended_action = "立即停止项目并进行紧急医疗分流，同时记录并升级负责人。";
    } else if (diagnosed) {
      normalized.answer = "您提到已有相关诊断。点阵波不能替代医疗诊断、手术或医生制定的治疗方案，也不能仅凭聊天判断今天是否适合体验。请先由负责诊疗的医疗人员结合当前情况确认；如果出现麻木、无力、胸痛、呼吸困难、晕厥或其他新异常，请停止项目并及时就医。";
      normalized.uncertainties = ["需要核实当前诊断、医疗建议、症状变化和项目适用性。"];
      normalized.recommended_action = "确认前不安排项目，先向负责诊疗的医疗人员核实。";
    } else {
      normalized.answer = "您提到的情况需要优先确认安全。现在先停止项目和销售沟通，不在门店判断原因；请尽快由医疗机构评估，并由门店负责人记录和跟进。";
      normalized.uncertainties = ["需要确认症状开始时间、程度、变化和伴随情况。"];
      normalized.recommended_action = "停止项目，完成负责人升级、记录和必要医疗分流。";
    }
    policyOwnedAction = true;
  } else if (isStaticPointWaveAftercareQuery(context)) {
    normalized.answer = staticPointWaveAftercareReply(context);
    normalized.uncertainties = ["需要确认开始时间、疼痛程度、变化和伴随症状。"];
    normalized.recommended_action = "暂停后续项目，完成风险问询、记录和负责人升级；必要时进行医疗分流。";
    policyOwnedAction = true;
  } else if (staticPostServiceAdverseEvent(context)) {
    const urgentAdverse = STATIC_POST_SERVICE_ADVERSE_URGENT_PATTERN.test(normalizeStaticSafetyText(context));
    normalized.answer = urgentAdverse ? STATIC_POST_SERVICE_ADVERSE_URGENT_REPLY : STATIC_POST_SERVICE_ADVERSE_REPLY;
    normalized.uncertainties = ["需要核实项目名称、服务时间、部位、症状程度和变化；门店不能在聊天中判断原因。"];
    normalized.recommended_action = urgentAdverse
      ? "立即停止项目并进行紧急医疗分流，同时记录并升级负责人。"
      : "暂停同部位后续项目，记录项目、时间、部位和变化，并联系实施机构或有资质人员核实；出现红旗症状立即医疗分流。";
    policyOwnedAction = true;
  } else if (route.stop_sales) {
    const surgeryQuestion = /替代手术/i.test(context);
    const affirmedContext = staticAffirmedSafetyText(context);
    const numbnessBoundary = /腿麻|手麻|麻木|无力/i.test(affirmedContext);
    normalized.answer = surgeryQuestion
      ? `点阵波不能替代手术、医疗诊断或医生制定的治疗方案。${numbnessBoundary ? "你已提到麻木或无力等症状，今天应先停止项目与销售推进，并由医疗机构评估；若症状持续、加重或伴随大小便异常、会阴麻木等情况，请及时就医或联系急救。" : "如果同时已有相关诊断，或出现麻木、无力等异常，应先由医疗机构评估，不要用项目体验替代医疗评估。"}`
      : numbnessBoundary
        ? "您提到持续不适并出现手麻、腿麻、麻木或无力，这需要先由医疗机构评估；今天先不要体验项目，也不要继续销售沟通。门店不能判断病因，也不能用项目体验替代医疗诊断或评估；症状持续或加重时请及时就医。"
      : followUp
        ? "现在先停止体验和销售沟通，不要自行判断原因。若胸痛、呼吸困难、晕厥、明显出冷汗或进行性麻木无力正在发生、持续或加重，请尽快联系急救或前往医疗机构；情况稳定后再由门店负责人记录并跟进。"
        : "您提到的情况需要先确认安全，今天先不要做项目，也不要继续产品推荐。请告诉我症状从什么时候开始、是否正在加重，以及有没有胸痛、呼吸困难、晕厥或进行性麻木无力；症状明显、持续或加重时，请尽快联系急救或前往医疗机构。";
    normalized.uncertainties = ["需要确认症状开始时间、程度、变化和伴随情况。"];
    normalized.recommended_action = "停止销售推进，完成风险问询、负责人升级和必要的医疗分流。";
    policyOwnedAction = true;
  } else if (/(?:背部|后背).{0,8}(?:凉|冷)|(?:凉|冷).{0,8}(?:背部|后背)|器官功能/i.test(context)) {
    normalized.answer = "背部发凉是一种主观感受，不能据此判断某个器官功能不好，也不能由门店作疾病诊断。先确认从什么时候开始、是否持续或加重，以及有没有疼痛、麻木、无力、胸痛、呼吸困难、发热等伴随情况；症状明显、持续或伴随异常时应由医疗机构评估。";
    normalized.uncertainties = ["需要确认持续时间、变化、诱因和伴随症状。"];
    normalized.recommended_action = "先做风险问询；不能用项目体验替代医疗诊断或评估。";
    policyOwnedAction = true;
  } else if (/水分测试笔|水分(?:测试|数值|值)|含水量|含水(?:测试|数值)/i.test(context)) {
    normalized.answer = "这次水分数值可以作为当次记录。请尽量使用同一设备、同一部位、相近时间和环境，并记录护肤、清洁等条件；我会结合相同条件下的多次复测，和您一起看阶段变化。";
    normalized.uncertainties = ["需要确认设备、部位、时间、环境和前后测量条件是否一致。"];
    normalized.recommended_action = "按统一条件记录本次结果，约定后续复测，不把单次读数宣传为长期效果。";
    policyOwnedAction = true;
  } else if (/GLP-1|司美|减肥针|处方|药品|减肥药|口服片|剂量|停药|换药/i.test(context)) {
    const childContext = staticAffirmativeChildContext(context);
    const subject = childContext ? "儿童或未成年人的用药不能仅凭聊天判断是否适合，更需由监护人携带处方和药品信息与医生或药师核实。" : "药品适用性不能仅凭聊天判断。";
    normalized.answer = `${subject}具体药品的用法和剂量必须依据当前说明书与医生处方，门店不能给剂量，也不能建议开始、停用或更换药物。请携带药品包装和用药记录，由开药医生或药师核实。`;
    normalized.uncertainties = ["需要确认具体药品身份、处方、合并用药和当前症状。"];
    normalized.recommended_action = "暂停具体产品或剂量建议，咨询开药医生或药师。";
    policyOwnedAction = true;
  } else if (/孩子|儿童|未成年|孕妇|怀孕|备孕|哺乳|慢病|糖尿病|高血压|三高/i.test(context)) {
    normalized.answer = "这类情况不能仅凭聊天直接判断可以做。先暂停项目或产品推荐，确认具体年龄或阶段、疾病与用药、当前症状和产品或设备说明，再由有资质的医生、药师或相应专业人员确认。";
    normalized.uncertainties = ["需要更具体的健康信息、用药信息和产品说明。"];
    normalized.recommended_action = "确认前不操作、不销售具体方案，先转有资质人员核实。";
    policyOwnedAction = true;
  } else if (/敏感肌|皮肤过敏|容易过敏|医美恢复|泛红|刺痛|破损/i.test(context)) {
    normalized.answer = "不能只凭敏感肌判断能不能做。先确认目前有没有持续泛红、刺痛、破损、渗出或过敏发作，以及近期是否做过医美、刷酸、激光或使用强刺激产品；存在这些情况时先不操作，状态稳定后也要核对具体项目和成分。";
    normalized.uncertainties = ["需要确认当前皮肤状态、过敏史和近期项目史。"];
    normalized.recommended_action = "先完成肤况和项目适用性确认；无法确认时不操作。";
    policyOwnedAction = true;
  } else if (route.intent_id === "INTENT-PRICE" && !staticCurrentMessageRequestsDuration(current)) {
    normalized.answer = "我可以为您核对当前有效价格和权益。请告诉我您咨询的城市、门店、具体项目和日期，我会按当前生效版本为您确认。";
    normalized.uncertainties = ["需要确认城市、门店、具体项目、查询日期和当前生效版本。"];
    normalized.recommended_action = "确认门店与项目后查询当前系统。";
  } else if (route.intent_id === "INTENT-RESULT") {
    normalized.answer = "我理解您希望尽快看到变化。我会先和您确认最想改善的指标和既往情况，再按相同条件记录并做阶段观察；每个人的变化节奏会受到生活方式和个体差异影响，我会和您一起约定复盘时间。";
    normalized.uncertainties = ["需要确认具体项目、顾客目标和用于判断变化的指标。"];
    normalized.recommended_action = "先确定一个可观察指标和必要安全信息，再决定是否体验及何时复盘。";
  } else if (route.intent_id === "INTENT-COMPARISON") {
    normalized.answer = "我可以围绕您想改善的问题、可接受的体验、时间安排和必要安全信息逐项比较。请告诉我您正在比较的两个项目，以及最在意效果感受、时间还是预算中的哪一点。";
    normalized.uncertainties = ["需要确认正在比较的具体项目和最重要的选择标准。"];
    normalized.recommended_action = "先补齐比较对象和选择标准，再按当前课程与门店有效版本逐项说明。";
  } else if (!String(normalized.answer || "").trim() || String(normalized.answer).includes("演示模式")) {
    normalized.answer = `我会先围绕您当前最关心的问题整理已核验的信息：${route.focus || "先确认顾客目标和必要安全信息。"} 请告诉我具体想改善什么，以及这种情况大概持续多久，我会为您说明下一步。`;
    normalized.uncertainties = ["需要确认具体目标、持续时间和必要安全信息。"];
    normalized.recommended_action = route.recommended_next || "先补充一个必要信息，再确认下一步。";
  }
  if (!policyOwnedAction && STATIC_QA_UNSUPPORTED_PRODUCT_CLAIM_PATTERN.test(String(normalized.answer || ""))) {
    normalized.answer = "我会先确认您想改善的具体目标、当前状态和必要安全信息，再按已核验资料说明合适的项目边界、阶段安排和观察方式。";
    normalized.uncertainties = ["需要确认具体项目、顾客目标、当前状态和必要安全信息。"];
  }
  if (staticQaAnswerNeedsEmployeeVoiceRepair(normalized.answer)
    || (!policyOwnedAction && (!staticQaAnswerIsRelevant(normalized.answer, current, context, route)
      || !staticQaAnswerIsCurrentTurnRelevant(normalized.answer, current, context, route)))
    || (!controlledFaqAnswer && staticQaNeedsPositiveCustomerVoiceRepair(normalized.answer, current, context, route, policyOwnedAction))) {
    normalized.answer = staticQaCustomerVoiceFallback(current, context, route);
  }
  normalized.answer = String(normalized.answer || "暂时没有找到足够依据，请补充具体项目和最想解决的问题。").trim();
  normalized.uncertainties = Array.isArray(normalized.uncertainties) ? normalized.uncertainties.filter(Boolean).slice(0, 4) : [];
  if (!policyOwnedAction) {
    normalized.recommended_action = staticCurrentMessageRequestsDuration(current)
      ? "先确认具体项目和您想了解的是体验时长还是阶段变化，再按当前安排为您核对。"
      : staticPublicRecommendedAction(route);
  }
  normalized.route = publicStaticRoute(route);
  return normalized;
}

const STATIC_TRAINING_RED_FLAG_PATTERN = /胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|突发剧痛|进行性麻木|手(?:臂)?(?:新发|新|发)?麻|胳膊(?:新发|新|发)?麻|腿(?:部)?(?:新发|新|发)?麻|发麻|麻木|无力|发热|红肿|大小便异常|会阴麻木/i;
const STATIC_TRAINING_DISCOMFORT_PATTERN = /疼|痛|灼热|烫|头晕|不舒服|设备异常|设备报警|麻|无力/i;
const STATIC_TRAINING_UNVERIFIED_ADVICE_PATTERN = /(?:可能是|可能涉及|说明|属于).{0,14}(?:神经|损伤|炎症|病变)|(?:不要|立即|马上|建议|可以|应当|应该|先|让|安排|回家(?:后)?|在家).{0,16}(?:热敷|冷敷|冰敷|按摩|揉按|按揉|涂药|敷药|贴敷|在家观察|观察|自行(?:处理|护理)|休息|抬高|服药|停药|换药)|(?:热敷|冷敷|冰敷|按摩|揉按|按揉).{0,8}(?:手臂|腿|疼痛|发麻)|(?:(?:回家|在家).{0,10}(?:观察|等待|休息).{0,14}(?:\d+\s*(?:小时|天)|一两天|两天|三天|48小时|再说|看看))|(?:可以|建议|需要|先|马上|立即|回去|回家后?).{0,10}(?:服用|口服|吃)(?:一些|点|一)?(?:片|粒)?(?:布洛芬|双氯芬酸|对乙酰氨基酚|阿司匹林|止痛药|消炎药|处方药|药)|(?:服用|口服|吃)(?:一些|点|一)?(?:片|粒)?(?:布洛芬|双氯芬酸|对乙酰氨基酚|阿司匹林|止痛药|消炎药|处方药)|(?:把|将)?.{0,12}(?:司美格鲁肽|利拉鲁肽|贝那鲁肽|减肥药|处方药|用药).{0,8}(?:停了|停掉|换掉|换成)|(?:改成|改为|调整为|加到|减到).{0,12}(?:每天|每日|早晚|每次|\d+\s*(?:片|粒|次|毫克|mg))|(?:每次|每日|每天|早晚|饭前|饭后|睡前).{0,10}(?:毫克|mg|片|粒|次)|(?:治好|治愈|根治)/i;

function staticAffirmedCustomerText(value = "") {
  // Remove only the symptom directly covered by a negator.  Do not delete a
  // whole clause: “没有胸痛但手麻” must retain the affirmed hand numbness.
  return String(value || "").replace(STATIC_NEGATED_RED_FLAG_PATTERN, " ");
}

function staticVisibleCustomerText(scenario, history = []) {
  const visibleTurns = history
    .filter((item) => item?.role === "assistant")
    .map((item) => String(item.content || "").trim())
    .filter(Boolean);
  return staticAffirmedCustomerText([scenario?.opening || "", ...visibleTurns].join(" "));
}

function staticPointWaveBestReplyContext(scenario, history = []) {
  const scenarioText = `${scenario?.title || ""} ${scenario?.task || ""} ${scenario?.opening || ""}`;
  if (scenario?.module_id !== "MOD-03" || !scenarioText.includes("点阵波")) return false;
  const customerFacts = staticVisibleCustomerText(scenario, history);
  return /更痛|更疼|更酸痛|酸痛|疼痛加重|打坏/i.test(customerFacts)
    && !STATIC_TRAINING_RED_FLAG_PATTERN.test(customerFacts);
}

function staticEmployeeIntroducesOnlyHypotheticalRedFlag(employeeMessage = "") {
  // Feedback is produced before the customer's next turn.  A conditional
  // warning such as “如果手臂发麻” must stay conditional in the example reply.
  const original = normalizeStaticSafetyText(employeeMessage);
  return STATIC_RED_FLAG_SYMPTOM_PATTERN.test(original)
    && !STATIC_RED_FLAG_SYMPTOM_PATTERN.test(staticAffirmedSafetyText(original));
}

function staticHasAffirmativeEmployeeMatch(message, pattern) {
  const text = String(message || "");
  const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
  const matcher = new RegExp(pattern.source, flags);
  let match;
  while ((match = matcher.exec(text))) {
    const preceding = text.slice(0, match.index);
    const clauseStart = Math.max(...["，", "。", "；", "！", "？", ",", ".", ";", "!", "?"].map((mark) => preceding.lastIndexOf(mark))) + 1;
    const followingBoundaries = ["，", "。", "；", "！", "？", ",", ".", ";", "!", "?"]
      .map((mark) => {
        const position = text.indexOf(mark, match.index + match[0].length);
        return position < 0 ? Number.POSITIVE_INFINITY : position + (/[！？!?]/.test(mark) ? 1 : 0);
      });
    const clauseEnd = Math.min(...followingBoundaries, text.length);
    const clause = text.slice(clauseStart, clauseEnd);
    const clausePrefix = text.slice(clauseStart, match.index);
    const semanticPrefix = clausePrefix.split(/(?:但是|但|而是|可是|然而|不过|却|仍然?|还是|也|所以|因此|然后|同时)/i).at(-1) || "";
    const negated = /(?:不能|不可|不要|不应|不建议|不会|不用|不必|无需|无须|未必|不一定|不代表|不认为|不觉得|不承认|并不|绝不|不再|暂不|先不|停止|避免|拒绝|别)[^，。；！？,.;!?]{0,20}$/i.test(semanticPrefix)
      || /(?:不|不要|不能|不应|不会|不再|别).{0,16}(?:调低|降低|调小|减小|能量|力度|强度|档位).{0,12}$/i.test(semanticPrefix)
      || /(?:不是|并非)(?:要|让|叫|建议)?(?:你|您|我们)?$/i.test(semanticPrefix)
      || /不把.{0,12}(?:说成|解释成|当成)$/i.test(semanticPrefix)
      || /(?:不|不能|不可)算(?:是)?$/i.test(semanticPrefix)
      || /不$/i.test(semanticPrefix);
    const internallyNegated = !pattern.source.includes("不再继续")
      && /(?:不再|不会|不继续|不做|停止|暂停|终止).{0,10}(?:继续|做|操作|体验|项目|加量|打透)/i.test(match[0]);
    const questioned = (/[？?]/.test(clause) && /难道|是否|是不是|会不会|要不要|能不能|可不可以|有没有|怎么(?:能|会|可以)|为什么|为何/i.test(clause))
      || /(?:是否|是不是|算不算|可否)[^，。；！？,.;!?]{0,8}$/i.test(semanticPrefix);
    const directQuestionSuffix = /^[^，。；！,.;!]{0,10}(?:吗|么|呢)[？?]/i.test(text.slice(match.index + match[0].length));
    if (!negated && !internallyNegated && !questioned && !directQuestionSuffix) return true;
    if (!match[0].length) matcher.lastIndex += 1;
  }
  return false;
}

function staticTrainingMessageDeniesSafetyAction(message = "") {
  return staticHasAffirmativeEmployeeMatch(
    message,
    /(?:不用|不必|无需|无须|不要|不会|拒绝|别|不需要|没必要).{0,8}(?:暂停|停止|记录|登记|留档|上报|联系负责人|联系店长|就医|去医院|医疗评估|检查)|(?:不|别)(?:建议|需要).{0,8}(?:就医|去医院|医疗评估|检查)|(?:(?:回家|在家|先|等).{0,12}(?:睡一觉|睡一晚|睡一夜|等到?明天|明天再(?:说|看|处理|核对|安排)))/i,
  );
}

function staticTrainingSafeActionFlags(message = "") {
  const text = String(message || "");
  return {
    stopped: staticHasAffirmativeEmployeeMatch(text, /暂停|停止|先不(?:做|继续|安排)|不再继续(?:做|操作|安排)?|不继续|不会继续(?:做|操作|安排)?|绝不继续|不要继续|今天不(?:做|安排)|不做/i),
    keepsBoundary: staticHasAffirmativeEmployeeMatch(text, /不(?:要)?自行判断|无法判断|不能判断|不(?:在店内)?判断原因|不在店内(?:判断|诊断)|不做诊断|不能诊断/i),
    records: staticHasAffirmativeEmployeeMatch(text, /记录|登记|留档|核对上次/i),
    escalates: staticHasAffirmativeEmployeeMatch(text, /上报|升级处理|联系.{0,6}(?:负责人|店长)|负责人|店长/i),
    refers: staticHasAffirmativeEmployeeMatch(text, /就医|医疗|急救|医院|医生|专业评估|去检查|尽快检查/i),
    takesSeriously: staticHasAffirmativeEmployeeMatch(text, /重视|关注|需要注意|不能忽视|需要特别关注/i),
  };
}

function staticTrainingMessageHasUnsafeContradiction(message = "") {
  const text = String(message || "");
  const normalizes = staticHasAffirmativeEmployeeMatch(text, /(?:正常(?:反应|现象)?|没啥问题|没什么问题|没问题|没事|没关系|不要紧|不碍事|微损伤|自我修复|排寒反应|排毒反应)/i);
  const continues = staticHasAffirmativeEmployeeMatch(text, /(?:继续做|继续操作|接着做(?:完)?|照常(?:做|操作)|再做一次|把.{0,4}(?:项目|体验|操作)?做完|做完再说|明天.{0,4}可以做|加量|加大|加强|打透|不用停|不必停|没必要暂停|忍一忍|坚持一下|(?:辛苦.{0,6})?忍(?:上|个)?(?:几|两|三|四|五|六|七|八|九|十|\d+)分钟|(?:再|先)?忍(?:一)?(?:会儿?|会|片刻)|越痛越有效)/i);
  return staticCriticalHits(text).length > 0 || normalizes || continues || staticTrainingMessageDeniesSafetyAction(text);
}

function staticTrainingMessageHasCompleteSafeClosure(message = "") {
  const text = String(message || "");
  const actions = staticTrainingSafeActionFlags(text);
  return actions.stopped && actions.keepsBoundary && actions.records && actions.escalates && actions.refers
    && !staticTrainingMessageHasUnsafeContradiction(text);
}

function staticTrainingMessageHasSafeDirection(message = "") {
  const text = String(message || "");
  if (staticTrainingMessageDeniesSafetyAction(text)) return false;
  return Object.values(staticTrainingSafeActionFlags(text)).some(Boolean);
}

function staticTrainingSafetyDecision(scenario, history = [], message = "") {
  const employee = String(message || "");
  const customerFacts = staticVisibleCustomerText(scenario, history);
  const knownRedFlag = STATIC_TRAINING_RED_FLAG_PATTERN.test(customerFacts);
  const knownDiscomfort = STATIC_TRAINING_DISCOMFORT_PATTERN.test(customerFacts);
  const knownWorsening = /(?:做完|项目后|服务后|点阵波).{0,24}(?:更疼|更痛|疼痛加重|比.{0,8}(?:更重|还重|更痛))|(?:今天|现在).{0,14}(?:比.{0,8})?(?:更疼|更痛|还重|疼痛加重)/i.test(customerFacts);
  const minimizes = staticHasAffirmativeEmployeeMatch(employee, /(?:正常(?:反应|现象)?|没啥问题|没什么问题|没问题|没事|没关系|不要紧|不碍事|微损伤|自我修复|排寒反应|排毒反应)/i);
  const promisesImprovement = staticHasAffirmativeEmployeeMatch(employee, /(?:会|能|肯定|一定).{0,16}(?:更轻松|缓解|好转|恢复|越来越好)/i);
  const continues = staticHasAffirmativeEmployeeMatch(employee, /(?:继续做|继续操作|接着做(?:完)?|照常(?:做|操作)|再做一次|把.{0,4}(?:项目|体验|操作)?做完|做完再说|明天.{0,4}可以做|加量|加大|加强|打透|不用停|不必停|没必要暂停|忍一忍|坚持一下|(?:辛苦.{0,6})?忍(?:上|个)?(?:几|两|三|四|五|六|七|八|九|十|\d+)分钟|(?:再|先)?忍(?:一)?(?:会儿?|会|片刻)|越痛越有效)/i);
  const deniesSafety = staticTrainingMessageDeniesSafetyAction(employee);
  const unverifiedAdvice = staticHasAffirmativeEmployeeMatch(employee, STATIC_TRAINING_UNVERIFIED_ADVICE_PATTERN);
  const globalCritical = staticCriticalHits(employee).length > 0;
  const pointWaveBestContext = staticPointWaveBestReplyContext(scenario, history);

  if (pointWaveBestContext && matchesStaticPointWaveBestReply(employee)) {
    return {
      level: "good",
      issue: "你已使用点阵波服务后疼痛加重场景的安全回答，完成了承接、暂停、问询、记录升级和必要医疗分流。",
      why: "本轮先把疼痛加重作为需要跟进的异常处理，并完成暂停、问询和升级，符合安全优先的处理顺序。",
      method_step: "暂停服务并完成风险问询与升级",
      knowledge_focus: "点阵波服务后异常的安全承接与分流",
      suggested_reply: POINT_WAVE_BEST_REPLY,
      next_goal: "根据顾客下一轮补充的信息完成记录、负责人升级和跟进。",
    };
  }

  // A dangerous contradiction always wins, even when the same sentence also
  // contains safe words such as "暂停" or "就医".
  if (globalCritical || (knownWorsening && (minimizes || promisesImprovement || continues || deniesSafety || unverifiedAdvice)) || (knownRedFlag && (minimizes || promisesImprovement || continues || deniesSafety || unverifiedAdvice)) || (knownDiscomfort && (continues || unverifiedAdvice))) {
    const hasKnownRedFlag = knownRedFlag;
    return {
      level: "critical",
      issue: hasKnownRedFlag
        ? "顾客已明确出现需要优先处理的新症状，本轮却仍在弱化风险、拒绝安全处置或推进服务。"
        : "顾客已明确说服务后不适，本轮却仍建议继续、给出未核实的居家处置或将其说成正常。",
      why: hasKnownRedFlag
        ? "已知存在需要优先处理的新症状时，必须停止项目、保持不诊断边界，并完成记录上报和医疗分流。"
        : "已知服务后不适时不能继续推进、给出自行处理办法或保证之后会变轻，应先停止并完成必要安全处置。",
      method_step: "立即纠正风险表达并完成安全问询",
      knowledge_focus: "服务后变化、异常记录与必要分流",
      suggested_reply: hasKnownRedFlag
        ? "您刚才提到新的异常，我先把它作为需要跟进的安全情况处理，今天先为您停止后续安排。我会马上记录并请负责人跟进，同时建议您尽快到医疗机构评估。"
        : "我理解您会担心。疼痛比原来更明显时，我先把这个情况作为需要跟进的异常反应处理；今天我先为您暂停后续安排。麻烦您告诉我出现时间、部位和变化，以及有没有发热、肿胀、麻木或无力等新情况。",
      next_goal: hasKnownRedFlag ? "确认顾客理解暂停和医疗分流安排。" : "先问清时间、部位、变化和伴随情况，再给安全的下一步。",
    };
  }

  if (scenario?.id === "SCN-CEX-M03-S02") {
    const lowers = staticHasAffirmativeEmployeeMatch(employee, /调低|降低|调小|减小/i);
    const lowersThenContinues = lowers && staticHasAffirmativeEmployeeMatch(
      employee,
      /(?:调低|降低|调小|减小).{0,18}(?:继续(?:做|操作|体验|观察|感受)|再(?:做|操作|体验|试|忍|感受)|接着(?:做|操作|体验))/i,
    );
    if (lowersThenContinues) {
      return {
        level: "critical",
        issue: "顾客已经明确表示明显疼痛，本轮却提出降低能量后继续操作。",
        why: "明显疼痛时必须先尊重顾客停止权；降能量、继续观察或再试一次都不能代替暂停操作。",
        method_step: "立即停止操作并确认疼痛与伴随情况",
        knowledge_focus: "顾客停止权、明显疼痛与安全问询",
        suggested_reply: POINT_WAVE_IN_SESSION_PAUSE_REPLY,
        next_goal: "确认顾客当前状态，并完成记录和必要的负责人复核。",
      };
    }
    if (continues) {
      return {
        level: "critical",
        issue: "顾客已经明确表示明显疼痛，本轮却仍要求继续忍耐或降低力度后继续操作。",
        why: "明显疼痛时必须尊重顾客停止权，先停止操作并确认当前感受，不能用“忍几分钟”推进服务。",
        method_step: "立即停止操作并确认疼痛与伴随情况",
        knowledge_focus: "顾客停止权、明显疼痛与安全问询",
        suggested_reply: POINT_WAVE_IN_SESSION_PAUSE_REPLY,
        next_goal: "确认顾客当前状态，并完成记录和必要的负责人复核。",
      };
    }
    const actions = staticTrainingSafeActionFlags(employee);
    const priorSafePause = history.some((item) => item?.role === "user"
      && staticTrainingSafeActionFlags(item.content || "").stopped
      && !staticTrainingMessageHasUnsafeContradiction(item.content || ""));
    const asksDetail = /几分|酸胀|刺痛|电到|电击|麻木|发麻|无力|肿胀|红肿|发热|加重/i.test(employee);
    if (staticTrainingMessageHasCompleteSafeClosure(employee)
      || (actions.stopped && (actions.records || actions.escalates || actions.refers))) {
      return {
        level: "good",
        issue: "你已终止本次操作，并说明记录、负责人复核和必要的后续安全安排。",
        why: "顾客已表达明显疼痛，本轮优先停止、留痕并确认后续处理，承接了顾客当前担心。",
        method_step: "终止操作并完成记录升级",
        knowledge_focus: "停止权、异常记录与负责人复核",
        suggested_reply: employee,
        next_goal: "确认顾客接受安排，并给出具体联系或跟进时间。",
      };
    }
    if ((actions.stopped || priorSafePause) && asksDetail) {
      return {
        level: "good",
        issue: "你已先暂停操作，再追问疼痛程度、感觉或伴随变化，顺序正确。",
        why: "员工没有要求顾客继续忍耐，而是在停止后收集当前处理所需的信息。",
        method_step: "暂停后确认疼痛和伴随情况",
        knowledge_focus: "顾客停止权与必要安全问询",
        suggested_reply: employee,
        next_goal: "根据顾客回答决定终止、记录和负责人复核。",
      };
    }
    if (lowers) {
      return {
        level: "needs_work",
        issue: "顾客已明确表示明显疼痛；只提出降低能量，还没有先停止本次操作。",
        why: "降能量不能代替暂停。此时先让顾客停止忍耐和操作，再确认疼痛程度、感觉及伴随情况。",
        method_step: "先停止操作，再确认疼痛与伴随情况",
        knowledge_focus: "顾客停止权、明显疼痛与安全问询",
        suggested_reply: POINT_WAVE_IN_SESSION_PAUSE_REPLY,
        next_goal: "确认暂停后，根据顾客实际回答决定记录、负责人复核和后续安排。",
      };
    }
  }

  if ((knownRedFlag || knownWorsening) && staticTrainingMessageHasCompleteSafeClosure(employee)) {
    return {
      level: "good",
      issue: "你已明确暂停项目、不判断原因，并完成记录上报和必要的医疗分流。",
      why: "这些表达形成了完整的安全闭环，没有在店内诊断或继续推进服务。",
      method_step: "停止服务并完成安全升级",
      knowledge_focus: "异常记录、负责人升级与医疗分流",
      suggested_reply: knownRedFlag
        ? "您刚才提到新的异常，我先把它作为需要跟进的安全情况处理，今天先为您停止后续安排。我会马上记录并请负责人跟进，同时建议您尽快到医疗机构评估。"
        : "我先把这个情况作为需要跟进的异常反应处理，今天先为您暂停后续安排。我会马上记录并请负责人跟进；如果疼痛还在加重或出现新不适，我建议您尽快到医疗机构评估。",
      next_goal: "确认顾客理解安全安排，并完成记录、上报与跟进。",
    };
  }

  const acknowledges = /理解|担心|重视|抱歉|先不判断|不能先说|作为需要跟进|先把.{0,12}(?:异常|情况).{0,8}处理/i.test(employee);
  const pauses = staticTrainingSafeActionFlags(employee).stopped;
  const asksChange = /什么时候|何时|多久|是否.{0,6}加重|是否.{0,8}更重|比.{0,8}(?:重|疼|痛)|变化/i.test(employee);
  const asksCompanion = /伴随|(?:现在)?还有.{0,12}(?:不适|症状|反应|麻|无力|发热|红肿|胸痛|不舒服)|(?:有没有|是否|还有没有|现在还有).{0,12}(?:麻|无力|发热|红肿|胸痛|不舒服)|(?:有没有|是否|还有没有|现在还有).{0,12}(?:其他).{0,8}(?:不适|症状|反应)/i.test(employee);
  const priorSafePause = history.some((item) => {
    if (item?.role !== "user") return false;
    const prior = String(item.content || "");
    return staticTrainingSafeActionFlags(prior).stopped
      && !staticTrainingMessageHasUnsafeContradiction(prior);
  });
  if (knownWorsening && knownRedFlag && asksCompanion) {
    return {
      level: "needs_work",
      issue: "顾客已经明确出现新的麻木、无力或其他红旗症状，不应再把它当成尚未确认的信息重复询问。",
      why: "此时需要直接承接已知异常，完成暂停、记录、负责人升级和医疗分流。",
      method_step: "承接已知红旗并完成安全升级",
      knowledge_focus: "已知异常的记录、升级与医疗分流",
      suggested_reply: "您刚才提到麻木等新的异常，我先为您停止今天的后续安排。我会马上记录并请负责人跟进，同时建议您尽快到医疗机构评估。",
      next_goal: "确认顾客理解安全安排并完成记录、上报和跟进。",
    };
  }
  if (knownWorsening && asksCompanion) {
    if (pauses || priorSafePause) {
      return {
        level: "good",
        issue: "你在暂停后继续追问麻木、无力、发热或红肿等伴随情况，问询顺序正确。",
        why: "本轮只筛查尚未确认的伴随情况，没有把它们提前当作顾客已经出现的事实。",
        method_step: "在暂停后完成伴随情况筛查",
        knowledge_focus: "麻木、无力、发热、红肿等异常变化",
        suggested_reply: "我会继续围绕您刚才说的今天更重来处理，今天先为您暂停后续安排；现在还有麻木、无力、发热或红肿吗？我会把您的回答记录下来并请负责人跟进。",
        next_goal: "根据顾客下一轮实际补充的信息，决定记录升级和医疗分流。",
      };
    }
    return {
      level: "needs_work",
      issue: "你已追问伴随情况，但还没有先明确暂停今天的后续项目。",
      why: "服务后疼痛加重时应先暂停安排，再筛查时间、变化和伴随情况。",
      method_step: "先暂停，再完成伴随情况筛查",
      knowledge_focus: "服务后变化与安全问询顺序",
      suggested_reply: "我先为您暂停今天的后续安排。除了疼痛变化，您现在有没有麻木、无力、发热、红肿或其他新不适？",
      next_goal: "确认暂停后，根据顾客实际回答决定是否升级和分流。",
    };
  }
  if (knownWorsening && acknowledges && pauses && asksChange) {
    return {
      level: "good",
      issue: "你已经承接顾客的担心、先暂停后续安排，并追问疼痛开始时间和变化。",
      why: "本轮只使用顾客已经说出的“服务后更痛”来判断；先暂停、再问变化，符合安全优先的接待顺序。",
      method_step: "暂停安排并完成服务后变化问询",
      knowledge_focus: "出现时间、变化趋势与伴随情况",
      suggested_reply: "我理解您会担心。今天我先为您暂停后续安排；麻烦您告诉我疼痛从什么时候开始、现在是否还在加重，我会据此记录并请负责人跟进。",
      next_goal: "根据顾客下一轮实际补充的信息，再决定是否需要记录升级和医疗分流。",
    };
  }

  if (knownRedFlag && staticTrainingMessageHasSafeDirection(employee)) {
    return {
      level: "needs_work",
      issue: "你已经给出重视和就医的正确方向，但还没有明确暂停服务、保持不诊断边界，并完成记录上报。",
      why: "顾客在本轮之前已经说出新症状；建议就医是安全的，但处置流程仍需补齐。",
      method_step: "补齐暂停、记录上报和医疗分流",
      knowledge_focus: "红旗症状的安全闭环",
      suggested_reply: "您刚才提到新的异常，我先为您停止今天的后续安排。我会马上记录并请负责人跟进，同时建议您尽快到医疗机构评估。",
      next_goal: "确认顾客理解暂停和分流安排。",
    };
  }
  return null;
}

function staticTrainingSuggestedReplyFallback(scenario, history = []) {
  // The recommendation answers the *latest* customer turn.  Earlier turns
  // remain relevant only for disclosed safety context; they must not revive a
  // completed price/effect objection after the customer changes the question.
  const customerText = staticLatestCustomerMessage(history, scenario);
  const customerRiskText = staticVisibleCustomerText(scenario, history);
  if (scenario?.id === "SCN-CEX-M03-S02") return POINT_WAVE_IN_SESSION_PAUSE_REPLY;
  if (STATIC_TRAINING_RED_FLAG_PATTERN.test(customerRiskText)) return "您刚才提到新的异常，我会把它作为优先事项处理：先为您停止今天的后续安排，马上记录并请负责人跟进；同时建议您尽快到医疗机构评估。";
  if (staticPointWaveBestReplyContext(scenario, history)) return POINT_WAVE_BEST_REPLY;
  if (/价格|多少钱|费用|太贵|预算|优惠|活动/i.test(customerText)) return "我理解您想先把费用弄清楚。价格和活动会随城市、门店、具体项目和日期变化；请告诉我您咨询的城市、门店和项目，我再按当前有效标准为您核对。";
  if (/隐私|不想说|不愿回答|不想被问/i.test(customerText)) return "我理解您在意隐私。我会说明每项信息的用途，只了解与安全和服务安排直接相关的必要内容；您可以按自己的舒适度决定愿意提供哪些信息。";
  if (/一次|效果|有没有用|保证|反弹|多久/i.test(customerText)) return "我理解您在意做了是否值得。我先了解您最想改善的指标和当前情况，再说明可观察的记录方式和阶段复盘节点，您确认后再决定。";
  if (/热敷|区别|不一样|怎么弄|什么办法|适不适合|怕疼|怕痛/i.test(customerText)) return "我理解您想先把具体做法、差别和感受弄清楚，再决定是否体验。我先确认您最想改善的问题、持续时间和必要安全信息，再按已核验的信息向您说明。";
  return "我理解您想先把情况和可选方式弄清楚再决定。我先确认您最想改善的问题、持续时间和必要安全信息，再按已核验的信息向您说明，您确认后再决定。";
}

function staticTrainingSuggestedReplyIsRelevant(advice, scenario, history = []) {
  const reply = String(advice || "").trim();
  if (!reply) return false;
  const customerText = staticLatestCustomerMessage(history, scenario);
  const customerRiskText = staticVisibleCustomerText(scenario, history);
  const actions = staticTrainingSafeActionFlags(reply);
  const safeReply = actions.stopped
    && !staticTrainingMessageHasUnsafeContradiction(reply);
  if (scenario?.id === "SCN-CEX-M03-S02") return safeReply;
  if (STATIC_TRAINING_RED_FLAG_PATTERN.test(customerRiskText) || staticPointWaveBestReplyContext(scenario, history)) return safeReply;
  if (/价格|多少钱|费用|太贵|预算|优惠|活动|便宜/i.test(customerText)) return /价格|费用|预算|贵|便宜|价值|比较|差别|城市|门店|具体项目|日期|核对/i.test(reply);
  if (/隐私|不想说|不愿回答|不想被问/i.test(customerText)) return /隐私|用途|必要信息|可以不说|拒绝|同意|不急着/i.test(reply);
  if (/一次|有没有用|效果|保证|反弹|多久/i.test(customerText)) return /不承诺|不保证|目标|指标|记录|复测|复盘|阶段|个体差异|多久|什么变化/i.test(reply);
  return staticTrainingMessageIsRelevant(reply, history, scenario);
}

function staticTrainingSuggestedReplyNeedsRepair(advice, history = [], employeeMessage = "", allowEmployeeRepeat = false) {
  const reply = String(advice || "").trim();
  const placeholder = /(?:^|[^a-z])(?:X|Y|Z|TBD)(?:[^a-z]|$)|某(?:个|项|些|种|次|家|天|小时)|若干(?:次|天|小时|项)|待补充|待确认|占位符/i;
  const internal = /员工应该|建议话术|可以这样说|下一轮|本轮训练|评分|方法路由|knowledge_focus|method_step|suggested_reply|document_id|source_id|CHUNK/i;
  const policyVoice = /(?:疼痛|服务后|症状|异常).{0,16}(?:不能先|不能直接|需要先|必须先|应当先|应先).{0,36}|(?:当前|本次)(?:应|需要|先).{0,36}|(?:门店|在店内|聊天中).{0,16}(?:不能|不建议|不应).{0,36}/i;
  const ungrounded = /精准(?:控制|作用|放松).{0,12}(?:深度|范围|温度|肌肉)|更深层、?更均匀的?温热体验|促进(?:局部)?(?:血液)?循环|改善供血|增加供氧|疏通经络|微损伤|自我修复|痛则不通|排毒|排寒|燃脂|溶脂|产品可能不适合您当前.{0,10}(?:身体状态|用法)|调整(?:用法|方案|剂量).{0,12}(?:就会|会|能)(?:更合适|有效|改善)/i;
  const customerReplies = history.filter((item) => item?.role === "assistant").map((item) => String(item.content || "").trim());
  return reply.length < 20 || reply.length > 180 || (reply === String(employeeMessage || "").trim() && !allowEmployeeRepeat)
    || customerReplies.includes(reply) || (reply.match(/[？?]/g) || []).length > 1
    || STATIC_TRAINING_UNVERIFIED_ADVICE_PATTERN.test(reply) || placeholder.test(reply) || internal.test(reply) || policyVoice.test(reply) || ungrounded.test(reply);
}

function staticTrainingSuggestedReplyNeedsPositiveRepair(advice, scenario = {}, history = []) {
  const reply = String(advice || "").trim();
  if (!STATIC_UNNECESSARY_NEGATIVE_CUSTOMER_VOICE.test(reply)) return false;
  const customerText = staticLatestCustomerMessage(history, scenario);
  const customerRiskText = staticVisibleCustomerText(scenario, history);
  // Keep necessary stop, medical and prescription boundaries intact.  In all
  // ordinary coaching examples, a positive, executable phrasing is required.
  return !(
    scenario?.id === "SCN-CEX-M03-S02"
    || STATIC_TRAINING_RED_FLAG_PATTERN.test(customerRiskText)
    || staticPointWaveBestReplyContext(scenario, history)
    || /GLP-1|司美|利拉|贝那|减肥针|减肥药|处方|药品|用药|剂量|停药|换药|孩子|儿童|未成年|孕妇|怀孕|备孕|哺乳|慢病|糖尿病|高血压|三高/i.test(customerText)
  );
}

function sanitizeStaticTrainingSuggestedReply(feedback, scenario, history = [], employeeMessage = "", locallyVerifiedGood = false) {
  if (!staticTrainingSuggestedReplyNeedsRepair(feedback.suggested_reply, history, employeeMessage, locallyVerifiedGood)
    && staticTrainingSuggestedReplyIsRelevant(feedback.suggested_reply, scenario, history)
    && !staticTrainingSuggestedReplyNeedsPositiveRepair(feedback.suggested_reply, scenario, history)) return;
  feedback.suggested_reply = staticTrainingSuggestedReplyFallback(scenario, history);
}

const STATIC_TRAINING_FACT_MARKERS = ["手麻", "腿麻", "发麻", "麻木", "无力", "胸痛", "呼吸困难", "晕厥", "头晕", "发热", "红肿", "灼热", "设备异常"];

function staticTrainingTextMentionsUnknownFact(text, knownCustomerText) {
  return STATIC_TRAINING_FACT_MARKERS.some((marker) => !knownCustomerText.includes(marker) && String(text || "").includes(marker));
}

function staticTrainingTextClaimsUnknownFact(text, knownCustomerText) {
  return STATIC_TRAINING_FACT_MARKERS.some((marker) => {
    if (knownCustomerText.includes(marker) || !String(text || "").includes(marker)) return false;
    const escaped = marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const assertion = new RegExp(`(?:已(?:经)?|刚(?:刚)?|明确|目前|现在|新发|出现|伴有|补充|提到|说(?:了)?).{0,12}${escaped}|${escaped}.{0,8}(?:已(?:经)?|出现|加重|持续)`, "i");
    return assertion.test(String(text || ""));
  });
}

function staticTrainingFeedbackUsesCustomerOnlyText(feedback, history = [], employeeMessage = "") {
  const employeeText = [...history.filter((item) => item?.role === "user").map((item) => item.content || ""), employeeMessage].join(" ");
  const customerMessages = history.filter((item) => item?.role === "assistant").map((item) => String(item.content || "").trim()).filter(Boolean);
  const critique = [feedback.issue, feedback.why].map((item) => String(item || "")).join(" ");
  for (const match of critique.matchAll(/[‘“"']([^‘’“”"']{4,})[’”"']/g)) {
    const quoted = match[1];
    if (!customerMessages.some((customer) => customer.includes(quoted)) || employeeText.includes(quoted)) continue;
    const prefix = critique.slice(Math.max(0, match.index - 48), match.index);
    const suffix = critique.slice(match.index + match[0].length, match.index + match[0].length + 36);
    const lastEmployee = Math.max(prefix.lastIndexOf("员工"), prefix.lastIndexOf("你"));
    const lastCustomer = Math.max(prefix.lastIndexOf("顾客"), prefix.lastIndexOf("客户"));
    const employeeClause = lastEmployee >= 0 ? prefix.slice(lastEmployee) : "";
    const before = /(?:员工|你)(?:本轮|这句|当时|主动|直接|的)?(?:原话|回答|回复|表达|说法)?(?:是|为|说|表示|回复|回答|询问|问|提到|声称|承诺)[:：\s]*$/i.test(employeeClause);
    const after = /^[\s，,。；;:]*(?:是|就是|来自)(?:员工|你)(?:本轮|当时)?(?:的)?(?:原话|回答|回复|表达|说法)/i.test(suffix);
    if ((lastEmployee > lastCustomer && before) || after) return true;
  }
  return false;
}

function sanitizeStaticTrainingFutureClaims(feedback, fallback, scenario, history = []) {
  const knownCustomerText = staticVisibleCustomerText(scenario, history);
  let claimedUnknownFact = false;
  ["issue", "why", "method_step", "knowledge_focus", "next_goal"].forEach((key) => {
    if (staticTrainingTextClaimsUnknownFact(feedback[key], knownCustomerText)) claimedUnknownFact = true;
    if (staticTrainingTextMentionsUnknownFact(feedback[key], knownCustomerText)) feedback[key] = fallback[key];
  });
  if (staticTrainingTextClaimsUnknownFact(feedback.suggested_reply, knownCustomerText)) {
    claimedUnknownFact = true;
    feedback.suggested_reply = "我先根据您现在已经说明的情况来处理。这种变化从什么时候开始，现在是否加重，还有没有其他新的不适？";
  }
  if (claimedUnknownFact) feedback.level = fallback.level;
}

function staticHasKnownCurrentSafetyEvent(scenario = {}, history = []) {
  const customerRisk = staticVisibleCustomerText(scenario, history);
  return STATIC_TRAINING_RED_FLAG_PATTERN.test(customerRisk)
    || (/(?:加重|变重|更痛|更疼|比.{0,8}(?:重|痛|疼)|越来越(?:痛|疼))/i.test(customerRisk)
      && STATIC_TRAINING_DISCOMFORT_PATTERN.test(customerRisk))
    || staticPostServiceAdverseEvent(customerRisk);
}

function staticKnownSafetyContextFeedbackFallback(employeeMessage = "", scenario = {}, history = []) {
  // Keep every visible coach field anchored to the already disclosed safety
  // concern.  This is deliberately before generic relevance feedback.
  const customerRisk = staticVisibleCustomerText(scenario, history);
  const redFlag = STATIC_TRAINING_RED_FLAG_PATTERN.test(customerRisk);
  const pointWave = staticPointWaveBestReplyContext(scenario, history);
  let employeeExcerpt = String(employeeMessage || "").trim().slice(0, 60);
  if (redFlag) {
    return {
      level: "needs_work",
      issue: `顾客已经提到新的异常，本轮“${employeeExcerpt}”需要先承接这个情况并给出明确安排。`,
      why: "当前接待先围绕已知异常完成暂停、记录、负责人跟进和医疗分流，再进入其他沟通。",
      method_step: "承接已知异常并完成安全升级",
      knowledge_focus: "暂停、异常记录、负责人跟进与医疗分流",
      suggested_reply: staticTrainingSuggestedReplyFallback(scenario, history),
      next_goal: "下一轮根据顾客实际补充的信息确认跟进安排。",
    };
  }
  if (pointWave) {
    const hypotheticalRedFlag = staticEmployeeIntroducesOnlyHypotheticalRedFlag(employeeMessage);
    if (hypotheticalRedFlag) employeeExcerpt = "这句假设性说明";
    return {
      level: "needs_work",
      issue: `顾客已经表达点阵波服务后疼痛加重，本轮“${employeeExcerpt}”需要先承接这个担心并给出安全安排。`,
      why: "当前先把疼痛加重作为需要跟进的异常反应处理，完成暂停、问询、记录和负责人跟进，再根据实际情况安排后续。",
      method_step: "暂停后续安排并完成服务后变化问询",
      knowledge_focus: "点阵波服务后疼痛变化、异常记录与负责人跟进",
      suggested_reply: hypotheticalRedFlag ? POINT_WAVE_PAIN_CONTEXT_REPLY : POINT_WAVE_BEST_REPLY,
      next_goal: "下一轮根据顾客补充的时间、变化和伴随情况完成跟进。",
    };
  }
  return {
    level: "needs_work",
    issue: `顾客已经表达服务后的不适，本轮“${employeeExcerpt}”需要先承接当前情况并给出明确安排。`,
    why: "当前先围绕已知不适完成暂停、变化确认、记录和负责人跟进，再根据实际情况安排后续。",
    method_step: "承接服务后不适并完成必要安全问询",
    knowledge_focus: "服务后变化、异常记录与负责人跟进",
    suggested_reply: staticTrainingSuggestedReplyFallback(scenario, history),
    next_goal: "下一轮根据顾客实际补充的信息确认后续安排。",
  };
}

function staticCompleteSafeClosureFeedbackFallback(scenario = {}, history = [], employeeMessage = "") {
  const customerRisk = staticVisibleCustomerText(scenario, history);
  const hasSafetyContext = STATIC_TRAINING_RED_FLAG_PATTERN.test(customerRisk)
    || STATIC_TRAINING_DISCOMFORT_PATTERN.test(customerRisk);
  if (hasSafetyContext) {
    return {
      level: "good",
      issue: "你已明确暂停项目、不判断原因，并完成记录上报和必要的医疗分流。",
      why: "这些表达形成了完整的安全闭环，不应被误判为继续操作或店内诊断。",
      method_step: "停止服务并完成安全升级",
      knowledge_focus: "异常记录、负责人升级与医疗分流",
      suggested_reply: "我会把您现在的情况作为优先事项处理：先为您停止今天的后续安排，马上记录并请负责人跟进；根据您现在的情况，也建议您尽快到医疗机构评估。",
      next_goal: "确认顾客理解安全安排，并完成记录、上报与跟进。",
    };
  }
  return {
    level: "needs_work",
    issue: "你给出了一套安全处置话术，但顾客当前并未表达不适或异常，没有回答当前顾虑。",
    why: "安全话术只能用于已出现的风险情境；普通咨询仍要先承接顾客正在问的价格、效果、差别或决策问题。",
    method_step: "回到顾客当前问题并只补一个必要信息",
    knowledge_focus: "当前顾虑、问题定位与下一步",
    suggested_reply: staticTrainingSuggestedReplyFallback(scenario, history),
    next_goal: "下一轮只练习承接顾客当前顾虑，不套用无关的安全模板。",
  };
}

function normalizeStaticTrainingFeedback(result, scenario, history, rubric, message, customerReply = "") {
  const fallback = staticMockProgressive("training", "turn", scenario, history, rubric, message).feedback;
  const provided = result?.feedback && typeof result.feedback === "object" ? result.feedback : {};
  const feedback = {};
  ["level", "issue", "why", "method_step", "knowledge_focus", "suggested_reply", "next_goal"].forEach((key) => {
    const value = String(provided[key] || "").trim();
    feedback[key] = value || fallback[key];
  });
  if (!new Set(["good", "needs_work", "critical"]).has(feedback.level)) feedback.level = "needs_work";
  sanitizeStaticTrainingFutureClaims(feedback, fallback, scenario, history);
  const safetyDecision = staticTrainingSafetyDecision(scenario, history, message);
  if (safetyDecision) Object.assign(feedback, safetyDecision);
  else if (staticTrainingMessageHasCompleteSafeClosure(message)) {
    Object.assign(feedback, staticCompleteSafeClosureFeedbackFallback(scenario, history, message));
  }
  else if (staticHasKnownCurrentSafetyEvent(scenario, history)) {
    Object.assign(feedback, staticKnownSafetyContextFeedbackFallback(message, scenario, history));
  }
  else if (feedback.level === "good" && !staticTrainingMessageIsRelevant(message, history, scenario)) {
    Object.assign(feedback, {
      level: "needs_work",
      issue: `本轮“${String(message || "").trim().slice(0, 60)}”没有回应顾客当前问题，不能仅凭模型的“很好”评价判为正确。`,
      why: "评分先要验证回答与顾客当前顾虑相关，再评价表达方式。",
      method_step: "承接当前问题并补一个必要信息",
      knowledge_focus: "顾客当前顾虑与场景目标",
      suggested_reply: staticTrainingSuggestedReplyFallback(scenario, history),
      next_goal: "下一轮先直接回应顾客现在问的事。",
    });
  }
  else if (staticTrainingFeedbackUsesCustomerOnlyText(feedback, history, message)) {
    Object.assign(feedback, {
      level: "needs_work",
      issue: `本轮只评价员工原话：“${String(message || "").trim().slice(0, 72)}”。顾客说过的话不能算成员工表达。`,
      why: "员工与顾客角色必须严格分开；本轮反馈只能引用当前员工原话和此前公开信息。",
      method_step: "只依据当前员工原话给出反馈",
      knowledge_focus: "对话角色归属与时序边界",
      next_goal: "下一轮继续只根据员工实际表达进行评价。",
    });
  }
  else if (!staticTrainingFeedbackIsCurrentTurnRelevant(feedback, message, history, scenario)) {
    Object.assign(feedback, staticCurrentTurnFeedbackFallback(scenario, history));
  }
  if (!safetyDecision && staticTrainingFeedbackNeedsPositiveRepair(feedback, history, scenario)) {
    Object.assign(feedback, staticCurrentTurnFeedbackFallback(scenario, history));
  }
  sanitizeStaticTrainingSuggestedReply(feedback, scenario, history, message, safetyDecision?.level === "good");
  return feedback;
}

function staticTrainingMessageIsRelevant(employeeMessage = "", history = [], scenario = {}) {
  const message = String(employeeMessage || "").trim();
  const compact = message.replace(/[\s，,。.！!？?]/g, "");
  if (compact.length < 5 || /^(?:好的?|好|明白|知道了|可以|没问题|嗯|行)+$/i.test(compact)) return false;
  if (/天气|吃饭|星座|新闻|周末去哪|电影/i.test(message)) return false;
  const customerText = staticLatestCustomerMessage(history, scenario);
  if (/价格|多少钱|费用|太贵|预算|优惠|活动|便宜/i.test(customerText)) return /价格|费用|预算|贵|便宜|价值|比较|差别|城市|门店|具体项目|日期|核对|哪一项最在意/i.test(message);
  if (/隐私|不想说|不愿回答|不想被问/i.test(customerText)) return /隐私|用途|必要信息|可以不说|拒绝|同意|不急着/i.test(message);
  if (/司美|利拉|贝那|GLP|减肥药|减肥针|药品|用药|剂量/i.test(customerText)) return /具体药品|处方|医生|药师|用药|剂量|包装|记录|症状|安全|核对|不能.{0,8}(?:停药|换药|给剂量)/i.test(message);
  if (/一次|有没有用|效果|保证|反弹|多久/i.test(customerText)) return /不承诺|不保证|目标|指标|记录|复测|复盘|阶段|个体差异|多久|什么变化/i.test(message);
  return /了解|理解|担心|目标|持续多久|什么时候|哪里|哪个部位|感受|影响|安全|暂停|停止|记录|核对|说明|具体|想改善|最在意|方案|项目|体验|下一步|[？?]/i.test(message);
}

function staticTrainingFeedbackIsCurrentTurnRelevant(feedback, employeeMessage = "", history = [], scenario = {}) {
  if (!feedback || typeof feedback !== "object") return false;
  const currentCustomer = staticLatestCustomerMessage(history, scenario);
  if (!currentCustomer || staticDialogueHasExplicitSafetyBoundary(currentCustomer)) return true;
  const currentTopics = staticDialogueStrongTopics(currentCustomer);
  if (!currentTopics.size) return true;
  for (const key of ["issue", "why", "method_step", "knowledge_focus", "next_goal", "suggested_reply"]) {
    const valueTopics = staticDialogueStrongTopics(feedback[key]);
    // A duration, project, or measurement question can be the one necessary
    // follow-up.  Keep the hard gate for competing concerns such as price,
    // pain, privacy, drugs, effects, and comparisons.
    const competingTopics = [...valueTopics].filter((topic) => !["time", "service", "measurement"].includes(topic));
    if (competingTopics.length && !competingTopics.some((topic) => currentTopics.has(topic))) return false;
  }
  const employeeTopics = staticDialogueStrongTopics(employeeMessage);
  const combined = ["issue", "why", "suggested_reply"].map((key) => String(feedback[key] || "").trim()).join(" ");
  if (combined.length >= 28
    && ![...staticDialogueTopicTags(combined)].some((topic) => currentTopics.has(topic) || employeeTopics.has(topic))
    && /暂停|就医|疼痛|价格|效果|隐私|药|项目/i.test(combined)) return false;
  return true;
}

function staticCurrentTurnFeedbackFallback(scenario = {}, history = []) {
  return {
    level: "needs_work",
    issue: "本轮可以先回应顾客刚才提出的重点，再补一个必要信息。",
    why: "这样能让顾客先得到直接回应，对话也能自然进入下一步。",
    method_step: "承接当前问题并补一个必要信息",
    knowledge_focus: "顾客当前问题、已知信息与明确下一步",
    suggested_reply: staticTrainingSuggestedReplyFallback(scenario, history),
    next_goal: "下一轮先直接回应顾客最新问题，再自然追问一个必要信息。",
  };
}

function staticTrainingFeedbackNeedsPositiveRepair(feedback, history = [], scenario = {}) {
  const customerContext = staticLatestCustomerMessage(history, scenario);
  if (staticDialogueHasExplicitSafetyBoundary(customerContext)) return false;
  return ["issue", "why", "method_step", "knowledge_focus", "next_goal"]
    .some((key) => STATIC_UNNECESSARY_NEGATIVE_CUSTOMER_VOICE.test(String(feedback?.[key] || "")));
}

const TEST_INTERNAL_MARKERS = /考核|评分|知识库|方法路由|隐藏异议|must_test|员工应该|培训教练/i;
const CUSTOMER_ROLE_DRIFT_MARKERS = /适用性确认|专业评估|医疗评估|红旗|禁忌|SOP|成分核对|设备型号|阶段指标|复盘|治疗史|特殊护肤品|强刺激产品|作用原理|工作原理|操作流程|测温|设备参数|产品机制|(?:建议|请)您|我建议(?:你|您)|你(?:应该|需要).{0,12}(?:询问|确认|了解|评估|说明)|您.{0,18}(?:有没有|是否|做过|用过|最近一次|病史|过敏史)/i;
const LIMITED_CUSTOMER_POLICY = `顾客认知边界（最高优先级）：顾客只知道自己的困扰、感受、生活情况和真实顾虑；最多听过一个模糊项目名，不知道原理、成分、设备、适用标准、禁忌或操作流程。只回答员工最新问题，每轮只说一个事实、感受或顾虑，通常15—60个汉字，最多问一个普通顾客会问的问题。不得替员工做需求分析、风险筛查或建议，不得反问员工的病史、医美史、过敏史、用药和护肤品。员工答错时可以不满意或要求重讲，但始终保持来咨询的普通顾客身份。不得使用适用性确认、专业评估、医疗评估、红旗、禁忌、SOP、成分核对、设备型号、阶段指标、复盘等专业词。员工只给出简单否定、空泛肯定（例如“有的”“可以”“好的”）或答非所问时，这不算已经回答顾客；先围绕原始困扰追问具体方法、项目或安排，只有员工给出相关实际说明后才进入下一条顾虑。`;

function staticCustomerScenario(scenario = {}, freeformCustomer = false) {
  const persona = scenario.persona || {};
  const context = {
    persona: Object.fromEntries(["age", "gender", "occupation", "style", "goal", "risk", "knowledge_level"].filter((key) => persona[key] != null && persona[key] !== "").map((key) => [key, persona[key]])),
    dialogue_mode: freeformCustomer ? "freeform_current_turn" : "scripted_release_compatibility",
  };
  if (!freeformCustomer) Object.assign(context, {
    hidden_objections: scenario.hidden_objections || [],
    hidden_information: scenario.hidden_information || [],
    information_release_rules: scenario.information_release_rules || [],
  });
  return context;
}

function staticPublicTrainingScenario(scenario = {}) {
  return {
    title: scenario.title || "",
    module_title: scenario.module_title || "",
    task: scenario.task || "",
    opening: scenario.opening || "",
  };
}

const CUSTOMER_VAGUE_EMPLOYEE_REPLY = /^(?:有|有的|有办法|有相关项目|可以|可以的|能做|好的|好|是的|对|对的|没问题|了解|知道)(?:[，。！!、,\s]*(?:有|的|办法|可以|好的|好|是的|对|对的|没问题|了解|知道))*[。！!，,、\s]*$/i;
const CUSTOMER_HOLD_REPLY_MARKERS = /没听明白|具体是什么办法|再具体说说|再说清楚|先介绍一下/i;

function staticCustomerClarificationReply(scenario, history = []) {
  const goal = String(scenario?.persona?.goal || "我现在这个困扰").trim();
  const lastCustomer = [...history].reverse().find((item) => item?.role === "assistant")?.content || "";
  if (/有没有|有适合|什么办法|什么方法|怎么|如何|方案|项目/.test(String(lastCustomer))) return "我还没听明白，具体是什么办法，适合我这种情况吗？";
  return `我还没听明白，能再具体说说吗？我主要还是想解决${goal}。`;
}

function staticFreeformCustomerClarificationReply(history = []) {
  const candidates = [
    "我还没完全听明白，您刚才说的具体安排是什么？",
    "我先听明白您刚才说的内容，再决定下一步怎么做，可以吗？",
    "您刚才讲的是这个问题，对吗？我还有一个细节想确认。",
    "我想先确认您刚才说的这一点，具体要怎么安排呢？",
  ];
  const previous = new Set(history.filter((item) => item?.role === "assistant").map((item) => String(item.content || "").trim()));
  return candidates.find((candidate) => !previous.has(candidate)) || candidates[0];
}

function staticEmployeeMessageNeedsCustomerClarification(history = [], employeeMessage = "") {
  const employee = String(employeeMessage || "").trim();
  if (!employee || CUSTOMER_VAGUE_EMPLOYEE_REPLY.test(employee)) return true;
  if (/我错了|说错了|不好意思|抱歉|不能做|做不了|没什么不同|没区别|都一样|不适合|多久|多长时间|什么时候开始|哪里|哪个部位|什么位置/.test(employee)) return false;
  if (employee.length <= 8 && !/[？?]/.test(employee)) return true;
  const lastCustomer = [...history].reverse().find((item) => item?.role === "assistant")?.content || "";
  const asksForMethod = /有没有|有适合|什么办法|什么方法|怎么|如何|方案|项目/.test(String(lastCustomer));
  return asksForMethod && !/方法|办法|方案|项目|体验|流程|步骤|安排|介绍|说明|适合/.test(employee);
}

function staticHiddenObjectionIndex(history = []) {
  const userTurns = history.filter((item) => item?.role === "user").length;
  const heldTurns = history.filter((item) => item?.role === "assistant" && CUSTOMER_HOLD_REPLY_MARKERS.test(String(item.content || ""))).length;
  return Math.max(0, userTurns - heldTurns);
}

function staticSafetyFlowCustomerReply(scenario, history = [], employeeMessage = "") {
  const customerFacts = staticVisibleCustomerText(scenario, history);
  if (!STATIC_TRAINING_RED_FLAG_PATTERN.test(customerFacts) || !staticTrainingMessageHasSafeDirection(employeeMessage) || staticTrainingMessageHasUnsafeContradiction(employeeMessage)) return "";
  if (staticTrainingMessageHasCompleteSafeClosure(employeeMessage)) {
    return "好的，那我先不做了。麻烦您帮我记录下来，也告诉我后面怎么联系负责人。";
  }
  return "好的，我会尽快去检查。那我今天是不是先不做任何项目了？";
}

function staticPointWaveReleaseReply(scenario, history = [], employeeMessage = "", candidateReply = "") {
  if (scenario?.id !== "SCN-CEX-M03-S01") return "";
  return staticGenericInformationReleaseReply(candidateReply, scenario, history, employeeMessage);
}

function staticPointWaveInSessionCustomerReply(scenario, employeeMessage = "") {
  if (scenario?.id !== "SCN-CEX-M03-S02") return "";
  const employee = String(employeeMessage || "").trim();
  const lowerEnergy = /(?:把|将)?(?:能量|力度|强度|档位).{0,8}(?:调低|降低|调小|减小|低一些|小一些|低一点|小一点)|(?:调低|降低|调小|减小).{0,8}(?:能量|力度|强度|档位)/i;
  const endure = /(?:忍|坚持).{0,8}(?:一会儿|一会|几分钟|一下|试试)|(?:再|先).{0,6}(?:忍|坚持)|继续.{0,6}(?:忍|坚持)/i;
  // The scenario starts with obvious pain.  Do not let the simulated customer
  // accept reduced energy or endurance in place of an explicit stop.
  if (staticHasAffirmativeEmployeeMatch(employee, lowerEnergy) || staticHasAffirmativeEmployeeMatch(employee, endure)) return "我已经很痛了，能不能先停下来？";
  const asks = (pattern) => staticEmployeeAffirmativelyAsksReleaseQuestion(employee, pattern);
  if (asks(STATIC_GENERIC_RELEASE_SINGLE_QUESTIONS["疼痛程度"])) return "大概8分。";
  if (asks(STATIC_GENERIC_RELEASE_SINGLE_QUESTIONS["感觉"]) || /(?:酸胀|刺痛).{0,20}(?:电到|电击).{0,8}[？?]/i.test(employee)) return "像电到一样。";
  const asksCompanion = asks(STATIC_GENERIC_RELEASE_SINGLE_QUESTIONS["伴随症状"]);
  const asksChange = asks(STATIC_GENERIC_RELEASE_SINGLE_QUESTIONS["变化"]) || /(?:加重|变重|更痛|更疼).{0,8}[？?]/i.test(employee);
  if (asksCompanion && asksChange) return "目前没有麻木、无力、明显肿胀或发热，暂停后也没有继续加重，就是还挺痛的。";
  if (asksCompanion) return "目前没有麻木、无力，也没有明显肿胀或发热，就是还挺痛的。";
  if (asksChange) return "暂停后没有继续加重，但现在还是挺痛的。";
  const safetyActions = staticTrainingSafeActionFlags(employee);
  if (staticTrainingMessageHasCompleteSafeClosure(employee)
    || (safetyActions.stopped && (safetyActions.records || safetyActions.escalates || safetyActions.refers))) {
    return "好，那今天就先不做了。麻烦您帮我记录一下，负责人什么时候能联系我？";
  }
  if (safetyActions.stopped) return "好，那先停下来。我现在还是挺痛的，接下来怎么处理？";
  return "";
}

const STATIC_GENERIC_RELEASE_ASK_MARKERS = /[？?]|(?:请|麻烦).{0,8}(?:说|告诉|提供)|(?:想|需要).{0,6}(?:了解|确认)|是否|有没有|有无|什么|怎么|如何|哪|几|多久|多长|吗|么|呢/i;
const STATIC_GENERIC_RELEASE_SHORT_FACTS = /成都|空腹|高血压|手麻|发麻|麻木|胸闷|胸痛|头晕|发热|无力|电击|备孕|结石|反黑|漏尿|出血|哺乳|便秘|晒伤|红肿|渗出|视物模糊|甲状腺|酸类|玻尿酸|经期|腰围|排便|不耐受|喝不下水|没吃早饭|眼周肿|异味|灌痛/gi;
const STATIC_GENERIC_RELEASE_NUMBER_FACTS = /(?:\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)(?:个)?(?:年|月|天|小时|分钟|分|厘米|次|袋)/gi;
const STATIC_GENERIC_RELEASE_DENIED_QUESTION = /(?:不是|并非).{0,10}(?:问|询问|追问|了解|确认)|(?:不|没|没有|无需|无须|不用|不必|不要|并不|不想|暂不|别).{0,4}(?:问|询问|追问|了解|确认)|(?:多久|多长时间|什么时候|何时|是否|有没有).{0,8}(?:不问|别问|不用问|无需问|不必问)/i;

const STATIC_GENERIC_RELEASE_COMPOUND_QUESTIONS = {
  "时间和变化": [/多久|多长时间|什么时候|何时|哪天|开始|持续/i, /变化|加重|变重|更重|更痛|更疼|越来越|减轻|好转|严重/i],
  "病史和进食": [/病史|高血压|慢性病|基础病/i, /进食|吃饭|吃东西|早饭|空腹/i],
  "饮食和经期": [/饮食|吃|聚餐/i, /经期|月经|例假|生理期/i],
  "复查和出血": [/复查|产后检查|检查过/i, /出血|流血|血性/i],
  "饮水排便": [/饮水|喝水|水喝/i, /排便|大便|便秘/i],
  "试感和停止方式": [/试感|试一下|小范围|先试/i, /停止|停下|随时停|叫停/i],
};

const STATIC_GENERIC_RELEASE_SINGLE_QUESTIONS = {
  "持续时间": /多久|多长时间|持续|几天|几个月|几年/i,
  "开始时间": /什么时候|何时|哪天|刚开始|开始时间/i,
  "产后时间": /产后.{0,6}(?:多久|时间)|生完.{0,6}多久|几个月/i,
  "伴随症状": /伴随|其他.{0,8}(?:不适|症状|反应)|有没有.{0,12}(?:麻|无力|发热|胸痛|胸闷|不舒服)/i,
  "门店": /门店|哪家店|哪个店|城市|地区|在哪里/i,
  "券名": /券名|券的名称|什么券|哪张券|券.{0,5}截图/i,
  "贵在哪里": /贵.{0,8}(?:哪|什么|原因|顾虑)|在意.{0,8}(?:价格|效果|预算)/i,
  "竞品包含内容": /竞品|别家|楼下|对方.{0,6}(?:包含|包括)|包了什么|做几次/i,
  "使用体验": /使用体验|用着|用了.{0,6}(?:感觉|觉得)|舒服|效果/i,
  "疼痛程度": /疼痛|疼|痛.{0,6}(?:程度|几分|多严重)|\d+\s*分/i,
  "感觉": /什么感觉|怎么痛|哪种感觉|感觉.{0,6}(?:像|是)|酸胀|刺痛|电到|电击/i,
  "进食饮水": /进食|吃饭|吃东西|早饭|空腹|饮水|喝水|喝不下/i,
  "变化": /变化|加重|变重|变大|扩大|更痛|更疼|越来越|减轻|好转|严重/i,
  "检查": /检查|报告|查过|复查/i,
  "症状": /症状|不适|哪里难受|痛|痒|灼|异味|分泌物/i,
  "测量": /测量|称重|什么时候称|早上|晚上/i,
  "其他指标": /其他指标|腰围|体围|体脂|除了体重/i,
  "餐次": /餐次|早餐|早饭|晚餐|一天几顿|怎么吃/i,
  "反应": /反应|不耐受|不舒服|过敏|红肿/i,
  "身体状态": /身体|状态|不舒服|乏力|头晕|精神/i,
  "用药": /用药|药物|吃药|服药|注射|打针/i,
  "特殊情况": /特殊情况|备孕|怀孕|哺乳|孕期/i,
  "病史": /病史|以前得过|慢性病|基础病|结石|高血压/i,
  "执行": /怎么.{0,6}(?:用|打|执行)|每天|频次|按计划/i,
  "营养": /营养|进食|吃得|食量|胃口/i,
  "复诊": /复诊|回诊|看过医生|定期检查/i,
  "怎么吃": /怎么吃|怎么喝|一天几袋|什么时候喝|代餐/i,
  "旧产品": /旧产品|以前的|哪个牌子|谁家|买了多久/i,
  "不适位置": /不适|哪里|位置|部位|钢圈|肩带|压痛/i,
  "主要问题": /主要|最想|哪个问题|困扰|诉求|目标/i,
  "目标": /目标|最想|想改善|想解决|在意|诉求/i,
  "既往产品": /既往|以前|之前|用过.{0,8}(?:产品|护肤品)|什么产品/i,
  "护肤": /护肤|刷酸|酸类|产品|昨晚用/i,
  "其他反应": /其他.{0,8}(?:反应|不适|症状)|眼周|呼吸|肿/i,
  "皮肤状态": /皮肤|皮肤状态|晒伤|暴晒|发红|破损/i,
  "皮肤": /皮肤|发红|红肿|表面|触痛/i,
  "既往反应": /既往|以前|之前|反应|红肿|过敏/i,
  "面部状态": /面部|脸型|脸.{0,5}(?:瘦|凹)|太阳穴|容量/i,
  "既往项目": /既往|以前|之前|做过.{0,8}(?:项目|填充|医美)|最近做/i,
  "既往史": /既往|以前|之前|激光|反黑|治疗过/i,
  "防晒": /防晒|暴晒|晒太阳|户外/i,
  "既往注射": /既往|以前|之前|注射|填充|打过什么/i,
  "眼部症状": /眼部|眼睛|视力|视物|模糊/i,
  "性生活": /性生活|性经历|伴侣|频率/i,
  "产后功能": /产后|盆底|漏尿|功能|憋不住/i,
  "使用产品": /使用.{0,6}(?:产品|洗液|药)|用了什么|洗液/i,
  "出血": /出血|流血|血性/i,
};

const STATIC_GENERIC_RELEASE_ACTIONS = {
  "堆叠项目": /项目.{0,28}项目|(?:所有|全部|全套|一整套|很多|多个).{0,8}项目/i,
  "直接承诺": /承诺|保证|肯定|一定|绝对|(?:可以|能).{0,8}(?:叠加|一起用)/i,
  "施压成交": /今天必须|现在就|马上.{0,6}(?:付款|购买|买|定)|不买.{0,8}(?:后悔|没有)|逼|必须买/i,
  "贬低原品牌": /原品牌.{0,8}(?:不好|没效|差|垃圾)|别的牌子.{0,8}(?:不好|没效|差)/i,
  "道歉并重新介绍": /抱歉|不好意思|是我.{0,6}(?:太快|没听清)|重新介绍|我是.{0,10}(?:顾问|负责|接待)/i,
  "继续解释套餐": /套餐|卡项|办卡/i,
  "建议继续做": /继续做|再做一次|加量|打透|照常做/i,
  "谈钱": /钱|价格|费用|浪费|退款/i,
  "否定按摩": /按摩.{0,8}(?:没用|无效|不好|不行)|不要.{0,5}按摩/i,
  "提医疗治疗": /医疗|治疗|医院|医生|就医/i,
  "说越热越好": /越热越好|热一点.{0,8}(?:更好|有效)|温度越高/i,
  "提出小范围试用": /小范围|小面积|先试用|试用一下/i,
  "提出试感和停止方式": /(?=.*(?:试感|试一下|小范围|先试))(?=.*(?:停止|停下|随时停|叫停))/i,
  "说继续": /继续做|继续操作|照常做|再做|加量/i,
  "承诺项目": /承诺|保证|一定|肯定|(?:能|可以).{0,8}(?:治好|解决|改善)/i,
  "承诺快速效果": /快速|马上|很快|一个月.{0,8}(?:减|瘦)|承诺.{0,8}(?:减|瘦)/i,
  "要求运动": /必须|要求|每天|每周|运动|锻炼/i,
  "直接推荐填充": /直接.{0,6}填充|现在.{0,6}填充|今天.{0,6}填充|建议.{0,6}填充/i,
  "直接推荐": /直接推荐|马上.{0,6}(?:用|做|开始)|就用这个|建议你.{0,8}(?:用|做|买)/i,
  "只建议观察": /再观察|先观察|回家观察|等一等|暂时不用处理/i,
  "给具体加量": /加量|多喝.{0,4}(?:一袋|两袋|\d+袋)|增加.{0,6}(?:用量|剂量)/i,
  "说正常": /正常反应|正常现象|这很正常|没问题|没事/i,
  "承诺不勒": /保证.{0,8}不勒|一定.{0,8}不勒|绝对.{0,8}不勒|不会勒/i,
  "默认组合": /两个.{0,8}(?:一起|组合)|组合.{0,8}(?:做|项目)|都给你安排/i,
  "安排马上做": /马上做|立即做|现在做|今天就做|当天做/i,
  "承诺一次": /一次.{0,8}(?:去净|解决|治好|有效)|保证.{0,8}一次|永久/i,
  "直接教凝胶用量": /凝胶.{0,10}(?:用量|剂量|次|毫升|克|次数)|每次.{0,8}凝胶/i,
};

function staticInformationReleaseRuleParts(rule) {
  const text = String(rule || "").trim();
  const delimiter = text.indexOf("时，");
  if (delimiter < 0) return ["", ""];
  return [text.slice(0, delimiter).replace(/^员工/, "").trim(), text.slice(delimiter + 2).replace(/[。.\s]+$/, "").trim()];
}

function staticEmployeeAffirmativelyAsksReleaseQuestion(employeeMessage, pattern) {
  const message = String(employeeMessage || "").trim();
  const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
  const matcher = new RegExp(pattern.source, flags);
  let match;
  while ((match = matcher.exec(message))) {
    const before = message.slice(0, match.index);
    const after = message.slice(match.index + match[0].length);
    const clausePrefix = before.split(/[，。；！？,.;!?]/).at(-1) || "";
    const clauseSuffix = after.split(/[，。；！？,.;!?]/)[0] || "";
    const clause = `${clausePrefix}${match[0]}${clauseSuffix}`;
    const deniedBefore = /(?:不是|并非).{0,8}(?:在)?(?:问|询问|追问|了解|确认).{0,8}$|(?:不|没|没有|无需|无须|不用|不必|不要|并不|不想|暂不|别).{0,4}(?:问|询问|追问|了解|确认).{0,8}$/i.test(clausePrefix);
    const deniedAfter = /^(?:先|就|我们|现在|暂时)?.{0,4}(?:不问|别问|不用问|无需问|无须问|不必问|不需要问)/i.test(clauseSuffix);
    if (!deniedBefore && !deniedAfter && STATIC_GENERIC_RELEASE_ASK_MARKERS.test(clause)) return true;
    if (!match[0].length) matcher.lastIndex += 1;
  }
  return false;
}

function staticEmployeeTriggersInformationReleaseRule(employeeMessage, rule) {
  const [condition] = staticInformationReleaseRuleParts(rule);
  const employee = String(employeeMessage || "").trim();
  if (!condition || !employee) return false;
  if (/^(?:问|询问|追问)/.test(condition)) {
    if (!STATIC_GENERIC_RELEASE_ASK_MARKERS.test(employee)) return false;
    const core = condition.replace(/^(?:问|询问|追问)/, "").replace(/^[“\"']|[”\"']$/g, "").trim();
    const compound = STATIC_GENERIC_RELEASE_COMPOUND_QUESTIONS[core];
    if (compound) return compound.every((pattern) => staticEmployeeAffirmativelyAsksReleaseQuestion(employee, pattern));
    const pattern = STATIC_GENERIC_RELEASE_SINGLE_QUESTIONS[core];
    if (pattern) return staticEmployeeAffirmativelyAsksReleaseQuestion(employee, pattern);
    const tokens = core.split(/和|及|、/).filter((token) => token.length >= 2);
    return Boolean(tokens.length) && tokens.every((token) => staticEmployeeAffirmativelyAsksReleaseQuestion(
      employee,
      new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"),
    ));
  }
  const pattern = STATIC_GENERIC_RELEASE_ACTIONS[condition];
  return pattern ? staticHasAffirmativeEmployeeMatch(employee, pattern) : false;
}

function staticInformationReleaseReply(rule) {
  const [, disclosure] = staticInformationReleaseRuleParts(rule);
  if (!disclosure) return "";
  const quoted = [...disclosure.matchAll(/[“\"]([^”\"]+)[”\"]/g)].map((match) => match[1]);
  if (quoted.length) {
    const text = String(quoted[0]).trim().replace(/[。！？!?]+$/, "");
    return `${text}${/[？?]/.test(quoted[0]) ? "？" : "。"}`;
  }
  const naturalResponses = [
    [/发送截图.*名称模糊/i, "我只能发一张截图，不过上面的名称有点模糊。"],
    [/顾客更反感/i, "你这样催我，我更不想现在决定了。"],
    [/顾客终止对话/i, "那我先不考虑了。"],
    [/顾客态度缓和/i, "好，那你先说说看。"],
    [/顾客愿意继续/i, "可以，那我们先小范围试试看。"],
    [/顾客马上同意/i, "那我今天就再做一次吧。"],
    [/顾客表示胸闷更明显/i, "我现在感觉胸闷更明显了。"],
    [/顾客表示害怕/i, "这么热我有点害怕，先停一下吧。"],
    [/顾客要求加热出更多汗/i, "那再加热一点，让我多出些汗吧。"],
    [/顾客说自己没看病/i, "我没有去医院看过，也没有诊断。"],
    [/顾客追问具体斤数/i, "那一个月具体能减多少斤？"],
    [/顾客说产品来自网络/i, "这个产品是我从网上买的。"],
    [/顾客说越来越严重/i, "可我感觉越来越严重了。"],
    [/顾客问是否能喝两袋/i, "那我可以一次喝两袋吗？"],
    [/顾客要求下周继续/i, "那我下周还可以继续做吗？"],
    [/顾客追问能否保证/i, "那你能保证一定不会勒吗？"],
    [/顾客说只想选一个/i, "我只想选一个项目，不想两个一起做。"],
    [/顾客要求写进合同/i, "那可以把这个保证写进合同吗？"],
    [/顾客问当天能否做/i, "那我今天可以直接做吗？"],
    [/顾客拒绝/i, "这个细节我不想回答。"],
  ];
  const natural = naturalResponses.find(([pattern]) => pattern.test(disclosure));
  if (natural) return natural[1];
  const payload = disclosure.replace(/^(?:顾客)?(?:说明|回答|说|表示|追问|要求)/, "").replace(/^[，,\s]+/, "").trim();
  if (!payload) return "我还想再了解清楚一点。";
  if (/^\d+分$/.test(payload)) return `大概${payload}。`;
  return `我这边的情况是：${payload.replace(/。$/, "")}。`;
}

function staticCompactReleaseText(value) {
  return String(value || "").trim()
    .replace(/^(?:顾客|客户|她|他)/, "")
    .replace(/昨夜|昨天晚上/gi, "昨晚")
    .replace(/今早|今晨|今天早上/gi, "今天")
    .replace(/胳膊/gi, "手臂")
    .replace(/木木(?:的)?|发木|发麻/gi, "麻木")
    .replace(/更厉害|更严重/gi, "更重")
    .replace(/[\s，,。.；;:：！!？?“”\"'、]/g, "");
}

function staticTextHasNewHiddenFragment(candidate, scenario, history = []) {
  const candidateCompact = staticCompactReleaseText(candidate);
  if (!candidateCompact) return false;
  const visibleCompact = staticCompactReleaseText(history.filter((item) => item?.role === "assistant").map((item) => item.content || "").join(" "));
  const disclosures = (scenario?.information_release_rules || []).map((rule) => staticInformationReleaseRuleParts(rule)[1]);
  const sources = [...(scenario?.hidden_information || []), ...disclosures];
  for (const source of sources) {
    const sourceCompact = staticCompactReleaseText(source);
    if (!sourceCompact) continue;
    for (let size = Math.min(10, sourceCompact.length); size >= 4; size -= 1) {
      for (let index = 0; index <= sourceCompact.length - size; index += 1) {
        const fragment = sourceCompact.slice(index, index + size);
        if (candidateCompact.includes(fragment) && !visibleCompact.includes(fragment)) return true;
      }
    }
    for (const pattern of [STATIC_GENERIC_RELEASE_NUMBER_FACTS, STATIC_GENERIC_RELEASE_SHORT_FACTS]) {
      pattern.lastIndex = 0;
      for (const match of sourceCompact.matchAll(pattern)) {
        const fragment = staticCompactReleaseText(match[0]);
        if (fragment && candidateCompact.includes(fragment) && !visibleCompact.includes(fragment)) return true;
      }
    }
    for (const match of String(source || "").matchAll(/[“\"]([^”\"]+)[”\"]/g)) {
      const fragment = staticCompactReleaseText(match[1]);
      if (fragment.length >= 2 && candidateCompact.includes(fragment) && !visibleCompact.includes(fragment)) return true;
    }
  }
  return false;
}

function staticGenericInformationReleaseReply(candidateReply, scenario, history = [], employeeMessage = "") {
  const rules = scenario?.information_release_rules || [];
  if (!rules.length) return "";
  const visibleCompact = staticCompactReleaseText(history.filter((item) => item?.role === "assistant").map((item) => item.content || "").join(" "));
  for (const rule of rules) {
    if (!staticEmployeeTriggersInformationReleaseRule(employeeMessage, rule)) continue;
    const reply = staticInformationReleaseReply(rule);
    if (reply && !visibleCompact.includes(staticCompactReleaseText(reply))) return reply;
  }
  const safetyFallback = staticSafetyFlowCustomerReply(scenario, history, employeeMessage);
  if (safetyFallback) return safetyFallback;
  const candidate = String(candidateReply || "").trim();
  const safetyDecision = staticTrainingSafetyDecision(scenario, history, employeeMessage);
  if (safetyDecision?.level === "critical" && /(?:好的|好|明白|可以).{0,16}(?:去检查|就医|先不做|暂停|帮我记录|联系负责人)/i.test(candidate)) {
    return "我还是不放心，你刚才这样说到底是什么意思？";
  }
  if (staticEmployeeMessageNeedsCustomerClarification(history, employeeMessage)) return staticCustomerClarificationReply(scenario, history);
  const previous = history.filter((item) => item?.role === "assistant").map((item) => String(item.content || "").trim());
  const repeated = previous.some((item) => candidate === item || (candidate.length >= 18 && item.length >= 18 && candidate.slice(0, 18) === item.slice(0, 18)));
  if (candidate
    && candidate !== String(scenario?.opening || "").trim()
    && !repeated
    && !invalidStaticCustomerReply(candidate)
    && !staticTextHasNewHiddenFragment(candidate, scenario, history)
    && !staticCustomerReplyNeedsContextRepair(candidate, employeeMessage, scenario)
    && staticCustomerReplyIsCurrentTurnRelevant(candidate, employeeMessage, history, scenario)) return candidate;
  const fallbackEmployee = STATIC_GENERIC_RELEASE_DENIED_QUESTION.test(String(employeeMessage || "")) ? "" : employeeMessage;
  return staticCustomerFallback(scenario, history, fallbackEmployee);
}

function staticCustomerFallback(scenario, history = [], employeeMessage = "", freeformCustomer = false) {
  const persona = scenario?.persona || {};
  const goal = String(persona.goal || "我现在这个困扰").trim();
  const employee = String(employeeMessage || "").trim();
  const explicitQuestion = /[？?]/.test(employee) || /(?:请|麻烦).{0,10}(?:说|告诉|补充)/i.test(employee);
  const safetyFlowReply = staticSafetyFlowCustomerReply(scenario, history, employee);
  if (safetyFlowReply) return safetyFlowReply;
  const safetyActions = staticTrainingSafeActionFlags(employee);
  if (safetyActions.stopped && (safetyActions.records || safetyActions.escalates || safetyActions.refers)) return "好，那今天就先不做了。麻烦您帮我记录一下，负责人什么时候能联系我？";
  if (safetyActions.stopped) return "好，那先停下来。我现在还是不太舒服，接下来怎么处理？";
  if (safetyActions.records || safetyActions.escalates) return "好，麻烦您帮我记下来。负责人什么时候能联系我？";
  if (/(?:有没有|是否|现在还有|还有没有)/.test(employee) && /麻木|发麻|无力|肿胀|红肿|发热|加重/.test(employee)) {
    const asked = staticExplicitSymptomTerms(employee);
    const labels = ["麻木", "无力", "发热", "红肿", "肿胀", "疼痛"].filter((term) => asked.has(term)).join("、") || "这些症状";
    return `我暂时没有留意到${labels}，目前最明显的还是疼痛比之前重。`;
  }
  if (explicitQuestion && /价格|多少钱|费用|预算|优惠|活动|太贵|便宜/i.test(employee)) {
    if (/效果|有没有用|见效|变化|一次/i.test(employee)) return "我现在更在意价格，想先把费用和能得到的服务弄清楚。";
    return "我想先把费用和活动弄清楚，再决定要不要继续了解。";
  }
  if (explicitQuestion && /效果|有没有用|见效|反弹|一次|几次/i.test(employee)) return "我更在意做了以后能看到什么变化，想先听您说明观察方式。";
  if (explicitQuestion && /区别|差别|对比|哪个|比较.{0,16}(?:吗|呢|？|\?)/i.test(employee)) return "我想先听明白这两个项目具体差在哪里，再结合自己的情况考虑。";
  if (explicitQuestion && /隐私|保密|不想说|不愿说/i.test(employee)) return "我比较在意自己的信息会怎么用，想先听您说清楚。";
  if (/我错了|说错了|不好意思|抱歉/.test(employee)) return `没关系，你重新给我讲清楚就行。我主要还是想解决${goal}。`;
  if (/不能做|做不了|没什么不同|没区别|都一样|不适合/.test(employee)) return `那我有点没听明白，我主要是${goal}，想知道还有没有别的办法。`;
  if (/多久|多长时间|什么时候开始/.test(employee)) return "有一阵子了，最近感觉比以前明显一些。";
  if (/哪里|哪个部位|什么位置/.test(employee)) return `主要就是${goal}，其他地方我暂时没太留意。`;
  if (/测量时间.{0,12}(?:不一样|不同)|结果.{0,10}(?:不一样|不同)|同一(?:时间|条件)/.test(employee)) return "明白了，那我之后尽量在相近时间、相近条件下测量。这样记录几天后再一起判断效果呢？";
  if (/不能直接说明|不能保证|连续趋势|测量条件|数据记录|再判断|再评估/.test(employee)) return "我明白，单次体重上涨不一定代表没有效果。那我们记录多久、达到什么变化时再一起判断呢？";
  if (String(scenario?.module_id || "") === "MOD-05" && /复测|记录|饮食|睡眠|运动|三到七天|一周后|相近时间|跟进/.test(employee)) return "好，那我先按相近时间复测，也把饮食、睡眠和运动记下来。到时候如果还是不降，我们再一起看看，可以吗？";
  if (/先做一次|做一次看看|先体验|安排体验|马上做|直接做|先安排/i.test(employee)) {
    if (String(scenario?.module_id || "") === "MOD-03") return "我现在问的是点阵波和我的情况，您还没说清怎么判断，怎么就要先做了？";
    if (String(scenario?.module_id || "") === "MOD-06") return "我问的是药品适不适合和需要核对什么，您还没回答，怎么就先安排了？";
    return "您还没回答我刚才的问题，怎么就先安排体验了？请先把这件事说清楚。";
  }
  if (staticEmployeeMessageNeedsCustomerClarification(history, employee)) return freeformCustomer ? staticFreeformCustomerClarificationReply(history) : staticCustomerClarificationReply(scenario, history);
  if (freeformCustomer) {
    // Live training/test customers only receive persona + opening context;
    // never fall back to hidden objections from the old scripted path.
    return staticFreeformCustomerClarificationReply(history);
  }
  const objections = scenario?.hidden_objections || [];
  const userTurns = staticHiddenObjectionIndex(history);
  if (userTurns >= objections.length) {
    const genericReplies = [`这些专业的我不太懂，我主要就是想解决${goal}。`, "我现在没有别的问题了，就是还没完全放心。", "那我先听到这里，想清楚以后再决定。", "我还得再想想，现在不想马上决定。", "我听明白一点了，不过心里还是有些犹豫。", "我主要担心的还是自己的情况到底能不能改善。"];
    return genericReplies[(userTurns - objections.length) % genericReplies.length];
  }
  const objection = objections[userTurns];
  if (/评分|员工|设置/.test(String(objection))) return "我最担心的是过程中会不会太痛或不舒服，能不能随时停下来？";
  const templates = {
    "怕疼": "我比较怕疼，过程中会不会很难受？",
    "太贵": "我也有点担心价格会不会太高。",
    "一次有没有用": "我还担心做一次看不到什么变化。",
    "时间": "我平时工作很忙，能安排出来的时间不多。",
    "固定斤数": "我还是很在意到底能不能瘦到自己想要的样子。",
    "价格": "我还要考虑预算，太贵的话可能不会做。",
    "成分/过敏": "我以前皮肤用东西容易不舒服，所以有点担心过敏。",
    "怕设备不安全": "我很怕烫，也担心过程中会不舒服。",
    "医院太贵": "我就是觉得去医院太贵了，所以才想先来问问。",
    "怕手术": "我一想到可能要做手术就很害怕。",
    "怕没效果": "我最怕花了钱却没什么变化。",
    "不信任": "我现在还不太放心，想先听你讲明白。",
    "一次见效": "我还担心做一次是不是看不出变化。",
    "疗效证据": "我以前试过不少方法都没坚持住，怕这次也没用。",
    "不想控制饮食": "如果还要管得特别严格，我可能坚持不了。",
    "回家考虑": "我还不想现在决定，想回去再考虑一下。",
    "药品身份": "我就是不确定这个到底算不算药，心里有点怕。",
    "疾病风险": "我有血糖问题，最担心会不会对身体有影响。",
    "价值不清": "我现在还没听明白贵在哪里。",
    "不愿回答问题": "我不太想说太多私人的事情。",
    "担心隐私": "我最在意的是隐私，不能接受的话我就不做。",
    "担心被强推": "我不希望一来就被一直推着买东西。",
    "担心异常": "我就是担心今天更酸痛是不是不正常。",
    "想继续购买": "如果这次没什么问题，我原本还想继续做。",
    "设备真伪": "我也分不清设备有什么区别，怕花冤枉钱。",
    "服务差异": "我看不出你们和别家到底差在哪里。",
  };
  const naturalObjection = String(objection || "").trim();
  const fallbackObjection = /^(?:担心|害怕|想|不想|在意|觉得|担忧)/.test(naturalObjection)
    ? `我现在主要还是${naturalObjection}`
    : `我现在主要还是担心${naturalObjection}`;
  return templates[objection] || `${fallbackObjection}，其他专业的我也不太懂。`;
}

function invalidStaticCustomerReply(reply) {
  const questionCount = (reply.match(/[？?]/g) || []).length;
  return !reply || reply.length > 100 || TEST_INTERNAL_MARKERS.test(reply) || CUSTOMER_ROLE_DRIFT_MARKERS.test(reply) || questionCount > 1;
}

function staticCustomerReplyHasDirectAnswer(reply, askedTopics = new Set()) {
  const text = String(reply || "").trim();
  if (/不太清楚|不确定|没留意|说不上来|记不清|不知道/i.test(text)) return true;
  if (askedTopics.has("time") && /\d+\s*(?:天|周|个月|月|年|小时|分钟)|[一二两三四五六七八九十半]+(?:天|周|个月|月|年)|刚(?:开始|才)|最近|上周|上个月|半年|一年/i.test(text)) return true;
  if (askedTopics.has("pain_safety") && /(?:有|没有|没|不太|目前|就是|还在).{0,14}(?:疼|痛|麻|无力|肿|热|头晕|不舒服)|\d+\s*分|[一二三四五六七八九十]\s*分|^(?:没有|没|有)[。！!，,\s]*$/i.test(text)) return true;
  if (askedTopics.has("price") && /\d+(?:\.\d+)?\s*(?:元|块|千|万)?|[一二三四五六七八九十]+千/i.test(text)) return true;
  if (askedTopics.has("location") && /(?:在|是).{0,12}(?:店|市|区|路)|北京|上海|广州|深圳|成都|杭州|武汉|重庆/i.test(text)) return true;
  return false;
}

function staticExplicitSymptomTerms(value) {
  const text = String(value || "").trim();
  const terms = new Set();
  const pairs = [
    ["麻木", /麻木|发麻|手麻|脚麻|腿麻|胳膊麻/i],
    ["无力", /无力|没劲|没力气|手没劲|腿没劲/i],
    ["发热", /发热|发烧|高热/i],
    ["红肿", /红肿|发红|红了一片/i],
    ["胸痛", /胸痛|胸口疼|胸闷/i],
    ["呼吸困难", /呼吸困难|喘不过气|气短/i],
    ["头晕", /头晕|眩晕/i],
    ["晕厥", /晕厥|昏厥|晕倒/i],
    ["肿胀", /肿胀|肿了|脸肿|眼周肿/i],
    ["灼热", /灼热|烧灼|火辣|烫/i],
    ["疼痛", /疼痛|疼|痛/i],
    ["过敏", /过敏|荨麻疹|风团/i],
    ["渗出", /渗出|流脓|破溃/i],
  ];
  pairs.forEach(([canonical, pattern]) => { if (pattern.test(text)) terms.add(canonical); });
  return terms;
}

function staticCustomerReplyIsCurrentTurnRelevant(reply, employeeMessage, history = [], scenario = {}) {
  const customerReply = String(reply || "").trim();
  const employee = String(employeeMessage || "").trim();
  if (!customerReply || !employee) return false;
  if (STATIC_QA_OFF_TOPIC_REPLY_PATTERN.test(customerReply)) return false;
  const askedTopics = staticDialogueStrongTopics(employee);
  const replyTopics = staticDialogueStrongTopics(customerReply);
  const directQuestion = /[？?]/.test(employee)
    || /(?:请|麻烦).{0,10}(?:说|告诉|补充)/i.test(employee)
    || /(?:有没有|是否|多久|多长时间|什么时候|哪里|哪个|哪家|价格|费用|效果|区别|适合)[^。；;！!]{0,18}(?:吗|呢)$/i.test(employee);
  const overlaps = [...askedTopics].some((topic) => replyTopics.has(topic));
  if (directQuestion) {
    const askedSymptoms = new Set([...staticExplicitSymptomTerms(employee)].filter((term) => term !== "疼痛"));
    if (askedSymptoms.size && ![...askedSymptoms].some((term) => staticExplicitSymptomTerms(customerReply).has(term))
      && !/不太清楚|不确定|没留意|说不上来|记不清|不知道|没注意到/i.test(customerReply)) return false;
    if (overlaps || staticCustomerReplyHasDirectAnswer(customerReply, askedTopics)) return true;
    // A short acknowledgement is never an answer to an explicit question.
    return !replyTopics.size && !/^(?:好|好的|明白|可以|行|嗯)[，。！!\s]*$/i.test(customerReply);
  }
  const actions = staticTrainingSafeActionFlags(employee);
  const hasAction = Object.values(actions).some(Boolean)
    || /我会|我们会|先为您|安排|记录|复测|核对|说明|解释|确认|暂停|停止/i.test(employee);
  const acknowledgement = /^(?:好|好的|明白|可以|行|嗯|谢谢|麻烦您|那就|我会|我配合|听懂)/i.test(customerReply);
  if (hasAction && replyTopics.size && askedTopics.size && !overlaps && !acknowledgement) return false;
  if (hasAction && replyTopics.size && askedTopics.size && !overlaps && acknowledgement && customerReply.length > 48) return false;
  return true;
}

function staticCustomerReplyNeedsContextRepair(reply, employeeMessage, scenario = {}) {
  const text = String(reply || "").trim();
  const employee = String(employeeMessage || "").trim();
  if (!text || !employee) return false;
  const planOrExplanation = /测量时间.{0,16}(?:不一样|不同)|结果.{0,12}(?:不一样|不同)|同一(?:时间|条件)|相近时间|复测|记录.{0,12}(?:饮食|睡眠|运动|数据)|连续趋势|三到七天|一周后|先把.{0,10}记录|再一起判断|暂停|停止|不再继续|调低|降低|记录|登记|上报|负责人|店长|就医|医疗机构|今天不做/.test(employee);
  if (!planOrExplanation) return false;
  if (/(?:这些专业的我不太懂|主要还是(?:想|担心|希望)|先听懂再决定|还没完全放心)/.test(text)) return true;
  const asksSafetyDetail = /有没有|是否|麻木|发麻|无力|肿胀|红肿|发热|加重|变重|几分|酸胀|刺痛|电到|电击/i.test(employee);
  const hasDirectAnswer = /没有|没发现|没留意|不清楚|不知道|有|麻|无力|肿|发热|加重|没有加重|\d+\s*分|[一二三四五六七八九十]\s*分|酸胀|刺痛|电到|电击|像电/i.test(text);
  if (asksSafetyDetail && !hasDirectAnswer) return true;
  const acknowledgment = /明白|好的|好，那|原来|我会|我先|听起来|可以|接受|理解/.test(text);
  return /[？?]/.test(text) && !acknowledgment && text.length <= 48;
}

function normalizeStaticCustomerReply(reply, scenario, history = [], employeeMessage = "", freeformCustomer = false) {
  let normalized = String(reply || "").trim();
  const inSessionReply = staticPointWaveInSessionCustomerReply(scenario, employeeMessage);
  if (inSessionReply) return inSessionReply;
  if ((scenario?.information_release_rules || []).length && !freeformCustomer) {
    // A rule-bearing scenario always resolves to one normalized release group
    // or a deterministic fallback; model-authored text never crosses the gate.
    if (scenario?.id === "SCN-CEX-M03-S01") return staticPointWaveReleaseReply(scenario, history, employeeMessage, normalized);
    return staticGenericInformationReleaseReply(normalized, scenario, history, employeeMessage);
  }
  const safetyFlowReply = staticSafetyFlowCustomerReply(scenario, history, employeeMessage);
  if (safetyFlowReply) return safetyFlowReply;
  const safetyDecision = staticTrainingSafetyDecision(scenario, history, employeeMessage);
  if (safetyDecision?.level === "critical" && /(?:好的|好|明白|可以).{0,16}(?:去检查|就医|先不做|暂停|帮我记录|联系负责人)/i.test(normalized)) {
    return "我还是不放心，你刚才这样说到底是什么意思？";
  }
  if (staticEmployeeMessageNeedsCustomerClarification(history, employeeMessage)) return staticCustomerClarificationReply(scenario, history);
  const previous = history.filter((item) => item?.role === "assistant").map((item) => String(item.content || "").trim());
  const repeated = previous.some((item) => normalized === item || (normalized.length >= 18 && item.length >= 18 && normalized.slice(0, 18) === item.slice(0, 18)));
  if (repeated || invalidStaticCustomerReply(normalized)
    || normalized === String(scenario?.opening || "").trim()) normalized = staticCustomerFallback(scenario, history, employeeMessage, freeformCustomer);
  if (staticCustomerReplyNeedsContextRepair(normalized, employeeMessage, scenario)
    || !staticCustomerReplyIsCurrentTurnRelevant(normalized, employeeMessage, history, scenario)) {
    normalized = staticCustomerFallback(scenario, history, employeeMessage, freeformCustomer);
  }
  return normalized;
}

function normalizeStaticTestTurn(result, scenario, history = [], employeeMessage = "", freeformCustomer = false) {
  const normalized = result && typeof result === "object" ? result : {};
  const reply = normalizeStaticCustomerReply(normalized.reply, scenario, history, employeeMessage, freeformCustomer);
  const emotions = new Set(["curious", "hesitant", "concerned", "relieved", "neutral"]);
  return { reply, emotion: emotions.has(normalized.emotion) ? normalized.emotion : "neutral", should_continue: normalized.should_continue !== false };
}

function staticAssessmentFailureMatches(history = []) {
  const matches = new Map();
  const add = (code, message) => {
    if (!matches.has(code)) matches.set(code, `员工原话：“${String(message || "").trim().slice(0, 180)}”`);
  };
  const continuePattern = /可以(?:继续)?做|还可以做|继续做|继续操作|接着做(?:完)?|照常(?:做|操作)|再做一次|把.{0,4}(?:项目|体验|操作)?做完|做完再说|加量|加大|安排项目|先体验|正常(?:反应|现象|的)?|没(?:啥|什么)?问题|没事|没关系|不要紧|不碍事|不用停|不必停|没必要暂停|忍一忍|坚持一下|(?:辛苦.{0,6})?忍(?:上|个)?(?:几|两|三|四|五|六|七|八|九|十|\d+)分钟|(?:再|先)?忍(?:一)?(?:会儿?|会|片刻)/i;
  const deferEscalationPattern = /(?:不(?:需|需要|用|必|建议)|无需|不用|没必要|暂不|先别|别|不急着).{0,12}(?:就医|去?(?:医院|急诊)|医疗评估|检查|联系医生)|(?:(?:回家|在家|先).{0,10}(?:观察|等待|休息).{0,16}(?:\d+\s*(?:小时|天)|一两天|两天|三天|48小时|一晚|一夜|今晚|再说|看看))|(?:(?:回家|在家|先|等).{0,12}(?:睡一觉|睡一晚|睡一夜|等到?明天|明天再(?:说|看|处理|核对|安排)))/i;
  const lowerEnergyPattern = /调低|降低|调小|减小/i;
  const lowerEnergyContinuationPattern = /(?:调低|降低|调小|减小).{0,18}(?:继续(?:做|操作|体验|观察|感受)|再(?:做|操作|体验|试|忍|感受)|接着(?:做|操作|体验))/i;
  const strongPainPattern = /(?:太|很|特别|非常|明显).{0,8}(?:疼|痛)|(?:疼|痛).{0,10}(?:受不了|不能忍|忍不住)|必须忍|忍几分钟|(?:[7-9]|10)\s*分/i;
  const refusalPattern = /不想|拒绝|不要触碰|不拍照|不愿意|别问了|回家考虑|和家人商量/i;
  const pressurePattern = /必须|今天就|现在就|一定要|不能拒绝|不买|不做.{0,8}(?:后悔|更严重)|别告诉|隐瞒/i;
  let priorCustomerText = "";
  let priorCustomerHasRedFlag = false;
  let priorCustomerHasDiscomfort = false;
  history.forEach((item) => {
    const message = String(item?.content || "").trim();
    if (!message) return;
    if (item?.role === "assistant") {
      priorCustomerText += ` ${message}`;
      const affirmed = staticAffirmedCustomerText(message);
      if (STATIC_TRAINING_RED_FLAG_PATTERN.test(affirmed)) priorCustomerHasRedFlag = true;
      if (STATIC_TRAINING_DISCOMFORT_PATTERN.test(affirmed)) priorCustomerHasDiscomfort = true;
      return;
    }
    if (item?.role !== "user") return;
    if (staticCriticalHits(message).length || staticHasAffirmativeEmployeeMatch(message, /(?:建议|应该|可以).{0,10}(?:停药|换药|剂量|口服|注射)/i)) add("CF-02", message);
    const unsafeContinuation = staticHasAffirmativeEmployeeMatch(message, continuePattern);
    // Only customer facts visible before this employee turn can trigger a
    // failure. A red flag disclosed by a later customer reply never travels
    // backwards into an earlier score.
    if (unsafeContinuation && priorCustomerHasRedFlag) add("CF-01", message);
    if (priorCustomerHasRedFlag && staticHasAffirmativeEmployeeMatch(message, deferEscalationPattern)) add("CF-01", message);
    const selfTreatment = staticHasAffirmativeEmployeeMatch(message, STATIC_ASSESSMENT_RECOVERY_SELF_TREATMENT);
    if (priorCustomerHasRedFlag && selfTreatment) add("CF-01", message);
    if (staticHasAffirmativeEmployeeMatch(message, pressurePattern) && refusalPattern.test(priorCustomerText)) add("CF-03", message);
    if (unsafeContinuation && priorCustomerHasDiscomfort) add("CF-04", message);
    if (priorCustomerHasDiscomfort && selfTreatment) add("CF-04", message);
    const strongPainKnown = strongPainPattern.test(staticAffirmedCustomerText(priorCustomerText));
    const lowersEnergy = staticHasAffirmativeEmployeeMatch(message, lowerEnergyPattern);
    const lowersThenContinues = staticHasAffirmativeEmployeeMatch(message, lowerEnergyContinuationPattern);
    const stopped = staticTrainingSafeActionFlags(message).stopped;
    if (priorCustomerHasDiscomfort && strongPainKnown && (lowersThenContinues || (lowersEnergy && !stopped))) add("CF-04", message);
  });
  return [...matches].map(([code, evidence]) => ({ code, evidence }));
}

function detectStaticAssessmentFailures(history = []) {
  return staticAssessmentFailureMatches(history).map((item) => item.code);
}

function staticAssessmentRedFlagWithoutCompleteSafeClosure(history = []) {
  let redFlagDisclosed = false;
  let safeClosureAfterDisclosure = false;
  history.forEach((item) => {
    const message = String(item?.content || "").trim();
    if (!message) return;
    if (item?.role === "assistant") {
      if (STATIC_TRAINING_RED_FLAG_PATTERN.test(staticAffirmedCustomerText(message))) redFlagDisclosed = true;
      return;
    }
    if (item?.role === "user" && redFlagDisclosed && staticTrainingMessageHasCompleteSafeClosure(message)) {
      safeClosureAfterDisclosure = true;
    }
  });
  return redFlagDisclosed && !safeClosureAfterDisclosure;
}

const STATIC_ASSESSMENT_DIMENSION_PATTERNS = {
  D1: /您好|欢迎|请坐|理解|谢谢|抱歉|听到您|我明白/i,
  D2: /了解|多久|持续|目标|作息|饮食|活动|尝试|影响|担心|最想改善|什么时候/i,
  D3: /不能|不承诺|不保证|个体差异|已核验|门店标准|体验|记录|复盘|核对/i,
  D4: /时间|预算|选择|安排|目标|部位|方案|下一步|核对/i,
  D5: /理解|担心|顾虑|在意|不承诺|选择|您看|先不急|再决定/i,
  D6: /安全|健康|暂停|停止|不舒服|异常|医疗|评估|记录|上报|负责人/i,
  D7: /下一步|愿意|安排|复盘|确认|跟进|联系|核对|再决定/i,
};

function staticEmployeeHistorySupportsDimension(dimensionId, history = []) {
  const pattern = STATIC_ASSESSMENT_DIMENSION_PATTERNS[dimensionId];
  return Boolean(pattern && history.some((item) => item?.role === "user" && pattern.test(String(item.content || ""))));
}

function staticFallbackEmployeeEvidence(dimensionId, history = []) {
  const employeeMessages = history.filter((item) => item?.role === "user" && String(item.content || "").trim()).map((item) => String(item.content).trim());
  const selected = [...employeeMessages].reverse().find((message) => (STATIC_ASSESSMENT_DIMENSION_PATTERNS[dimensionId] || /$^/).test(message)) || "";
  return selected ? `员工原话：“${selected.slice(0, 180)}”` : "对话中未体现";
}

function staticEvidenceSupportsDimension(dimensionId, evidence) {
  return (STATIC_ASSESSMENT_DIMENSION_PATTERNS[dimensionId] || /$^/).test(String(evidence || ""));
}

function staticEvidenceUsesCustomerOnlyText(evidence, history = []) {
  const employeeText = history.filter((item) => item?.role === "user").map((item) => item.content || "").join(" ");
  const customerMessages = history.filter((item) => item?.role === "assistant").map((item) => String(item.content || "").trim());
  for (const match of String(evidence || "").matchAll(/[‘“"']([^‘’“”"']{4,})[’”"']/g)) {
    const quoted = match[1].trim();
    if (employeeText.includes(quoted) || !customerMessages.some((message) => message.includes(quoted))) continue;
    const prefix = evidence.slice(Math.max(0, match.index - 48), match.index);
    const suffix = evidence.slice(match.index + match[0].length, match.index + match[0].length + 36);
    const lastEmployee = Math.max(prefix.lastIndexOf("员工"), prefix.lastIndexOf("你"));
    const lastCustomer = Math.max(prefix.lastIndexOf("顾客"), prefix.lastIndexOf("客户"));
    const employeeClause = lastEmployee >= 0 ? prefix.slice(lastEmployee) : "";
    const before = /(?:员工|你)(?:的)?(?:原话|回答|回复|表达|说法)?(?:是|为|说|表示|回复|回答|询问|问|提到)[:：\s]*$/i.test(employeeClause);
    const after = /^[\s，,。；;:]*是(?:员工|你)(?:的)?(?:原话|回答|回复|表达|说法)/i.test(suffix);
    if ((lastEmployee > lastCustomer && before) || after) return true;
  }
  return false;
}

function staticEvidenceIsGroundedInEmployee(evidence, history = []) {
  if (String(evidence || "").includes("对话中未体现")) return true;
  const employeeMessages = history
    .filter((item) => item?.role === "user" && String(item.content || "").trim())
    .map((item) => String(item.content).trim());
  if (!employeeMessages.length) return false;
  const quoted = [...String(evidence || "").matchAll(/[“"]([^”"]+)[”"]/g)].map((match) => match[1].trim()).filter(Boolean);
  if (quoted.length) return quoted.some((value) => employeeMessages.some((message) => message.includes(value)));
  const compact = (value) => String(value || "").replace(/[\s，,。.；;:：！!？?“”"'、]/g, "");
  const evidenceCompact = compact(evidence);
  return employeeMessages.some((message) => {
    const messageCompact = compact(message);
    if (messageCompact.length < 6) return Boolean(messageCompact) && evidenceCompact.includes(messageCompact);
    for (let index = 0; index <= messageCompact.length - 6; index += 1) {
      if (evidenceCompact.includes(messageCompact.slice(index, index + 6))) return true;
    }
    return false;
  });
}

const STATIC_ASSESSMENT_SPECIFIC_ADVICE = /(?:古方|口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物|隔天一次|每天\s*\d+\s*次)/i;
const STATIC_ASSESSMENT_CONCRETE_ADVICE = /(?:\d+(?:\.\d+)?\s*(?:mg|g|ml|毫克|克|毫升|片|粒|支|单位))|(?:(?:每天|每日|每周|每次|隔天|早晚|睡前|餐前|餐后).{0,8}(?:\d+|一|两|二|三|四|五|六|七|八|九|十).{0,3}次)|(?:(?:口服|注射).{0,12}(?:\d+|一|两|二|三|四|五|六|七|八|九|十)\s*(?:次|片|粒|支|毫升|毫克|mg|ml))/i;
const STATIC_ASSESSMENT_SAFE_ADVICE_BOUNDARY = /(?:(?:具体)?(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物)[^，,。；;！？!?\n]{0,18}(?:交由|由|请|需|需要|应|应该|须|必须)[^，,。；;！？!?\n]{0,10}(?:医生|医师|药师|医疗机构)[^，,。；;！？!?\n]{0,14}(?:评估|决定|指导|核实|开具|处方))|(?:(?:医生|医师|药师|医疗机构)[^，,。；;！？!?\n]{0,14}(?:评估|决定|指导|核实|开具|处方)[^，,。；;！？!?\n]{0,18}(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物))|(?:(?:门店|我们|员工)[^，,。；;！？!?\n]{0,8}(?:不能|不可|不会|不应|不得|不建议|不提供|不决定|不调整|无权)[^，,。；;！？!?\n]{0,14}(?:给出?|提供|建议|决定|调整|安排)?(?:具体)?(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物))|(?:(?:不能|不可|不要|不得|不建议|避免)[^，,。；;！？!?\n]{0,8}(?:自行|擅自)[^，,。；;！？!?\n]{0,5}(?:停换药|停药|停用|换药|更换药物|调整用药))|(?:(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物)[^，,。；;！？!?\n]{0,8}(?:遵医嘱|按医嘱))/gi;
const STATIC_ASSESSMENT_RECOVERY_SELF_TREATMENT = /(?:(?:建议|可以|应当|应该|先|让|安排|回家(?:后)?|在家|只要|无需|不必|等).{0,16}(?:热敷|冷敷|冰敷|按摩|揉按|按揉|涂药|敷药|贴敷|在家观察|观察|自行(?:处理|护理)|休息|抬高))|(?:(?:热敷|冷敷|冰敷|按摩|揉按|按揉|涂药|敷药|贴敷|在家观察|观察|自行(?:处理|护理)|休息|抬高).{0,16}(?:即可|就好|再说|看看|观察(?:\s*\d+)?(?:小时|天)?|(?:会)?(?:好|缓解|恢复|消退)|后再|然后))|(?:(?:(?:回家|在家).{0,10})?(?:观察|等待|休息).{0,14}(?:\d+\s*(?:小时|天)|一两天|两天|三天|48小时|再说|看看))/i;
const STATIC_ASSESSMENT_SAFE_RECOVERY_BOUNDARY = /(?:不(?:建议|要|应|可|宜)|避免|不得|不能|不可).{0,16}(?:热敷|冷敷|冰敷|按摩|揉按|按揉|涂药|敷药|贴敷|在家观察|观察|自行(?:处理|护理)|休息|抬高)/i;
const STATIC_ASSESSMENT_UNVERIFIED_CAP_CLAIM = /(?:关键失败|严重违规|触发\s*CF-?\d+).{0,28}(?:封顶|上限|最高|不超过|\d{1,3}\s*分)|(?:总分|分数).{0,16}(?:封顶|上限|最高|不超过)/i;
const STATIC_ASSESSMENT_COMMENT_BOUNDARY = "员工尚未把顾客顾虑转化为可执行的下一步。建议先澄清时间、预算和服务偏好，再给出门店当前已核验且符合安全边界的选择。";
const STATIC_ASSESSMENT_IMPROVEMENT_BOUNDARY = "不要替顾客给出具体的居家恢复、自行处理或用药安排；先核验适用条件和门店当前标准，再提供非医疗、可选择的下一步。";
const STATIC_ASSESSMENT_STRENGTH_BOUNDARY = "完成了基本沟通；涉及医疗决定、居家恢复或自行处理时仍需明确门店边界，并交由有资质人员评估。";
const STATIC_ASSESSMENT_FAILURE_REASON_BOUNDARY = "员工表达涉及未经核验的居家恢复、自行处理或具体用药安排，应明确门店边界并交由有资质人员评估。";
const STATIC_ASSESSMENT_SUMMARY_BOUNDARY = "本轮需要加强需求分析和个性化表达。后续重点练习在不承诺结果、不擅自补充居家恢复、自行处理或具体用药安排的前提下，把顾客顾虑转化为可执行的服务下一步。";

function staticAssessmentAdviceNeedsSanitizing(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.split(/[。；;！？!?\n]+/).some((sentence) => {
    if (STATIC_ASSESSMENT_SPECIFIC_ADVICE.test(sentence)) {
      // Concrete amounts and frequencies are never repeated in an assessment,
      // even when the same sentence also contains a disclaimer.
      if (STATIC_ASSESSMENT_CONCRETE_ADVICE.test(sentence)) return true;
      const remainder = sentence.replace(STATIC_ASSESSMENT_SAFE_ADVICE_BOUNDARY, "");
      if (STATIC_ASSESSMENT_SPECIFIC_ADVICE.test(remainder)) return true;
    }
    if (STATIC_ASSESSMENT_RECOVERY_SELF_TREATMENT.test(sentence)) {
      const remainder = sentence.replace(STATIC_ASSESSMENT_SAFE_RECOVERY_BOUNDARY, "");
      if (STATIC_ASSESSMENT_RECOVERY_SELF_TREATMENT.test(remainder)) return true;
    }
    return false;
  });
}

function sanitizeStaticAssessmentAdvice(result) {
  if (!result || typeof result !== "object") return result;
  (result.dimension_scores || []).forEach((dimension) => {
    if (dimension && typeof dimension === "object" && staticAssessmentAdviceNeedsSanitizing(dimension.comment)) {
      dimension.comment = STATIC_ASSESSMENT_COMMENT_BOUNDARY;
    }
  });
  [
    ["strengths", STATIC_ASSESSMENT_STRENGTH_BOUNDARY],
    ["improvements", STATIC_ASSESSMENT_IMPROVEMENT_BOUNDARY],
  ].forEach(([key, fallback]) => {
    if (Array.isArray(result[key])) {
      result[key] = result[key].map((item) => (staticAssessmentAdviceNeedsSanitizing(item) ? fallback : item));
    }
  });
  (result.critical_failures || []).forEach((failure) => {
    if (failure && typeof failure === "object" && staticAssessmentAdviceNeedsSanitizing(failure.reason)) {
      failure.reason = STATIC_ASSESSMENT_FAILURE_REASON_BOUNDARY;
    }
  });
  if (staticAssessmentAdviceNeedsSanitizing(result.summary)
    || (!(result.critical_failures || []).length && STATIC_ASSESSMENT_UNVERIFIED_CAP_CLAIM.test(String(result.summary || "")))) result.summary = STATIC_ASSESSMENT_SUMMARY_BOUNDARY;
  return result;
}

function normalizeStaticAssessment(result, history = [], rubric = {}, scenarios = state.scenarios || []) {
  const normalized = result && typeof result === "object" ? result : {};
  const specs = rubric.dimensions || [];
  const d6SafetyCeilingApplies = staticAssessmentRedFlagWithoutCompleteSafeClosure(history);
  const provided = new Map((Array.isArray(normalized.dimension_scores) ? normalized.dimension_scores : []).filter((item) => item?.id).map((item) => [item.id, item]));
  const dimensionScores = specs.map((spec) => {
    const item = provided.get(spec.id) || {};
    const maxScore = Number(spec.weight || spec.max_score || 0);
    const rawScore = Number(item.score);
    let score = Number.isFinite(rawScore) ? Math.max(0, Math.min(maxScore, Math.round(rawScore))) : 0;
    if (spec.id === "D6" && d6SafetyCeilingApplies) score = Math.min(score, 6);
    let evidence = String(item.evidence || "").trim();
    if (!evidence || staticEvidenceUsesCustomerOnlyText(evidence, history) || !staticEvidenceIsGroundedInEmployee(evidence, history) || !staticEvidenceSupportsDimension(spec.id, evidence) || !staticEmployeeHistorySupportsDimension(spec.id, history)) {
      evidence = staticFallbackEmployeeEvidence(spec.id, history);
      score = 0;
    }
    if (evidence.includes("对话中未体现")) score = 0;
    return { id: spec.id, name: spec.name, score, max_score: maxScore, evidence, comment: String(item.comment || "需要在下一轮对话中补充可验证表现。") };
  });
  const failureSpecs = new Map((rubric.critical_failures || []).map((item) => [item.code, item]));
  const detectedFailures = new Map(staticAssessmentFailureMatches(history).map((item) => [item.code, item.evidence]));
  // A focused/offline rubric may intentionally omit a production failure
  // code. Keep the local detector running, but only materialize failures
  // that this rubric can describe and score.
  const detectedFailureCodes = new Set([...detectedFailures.keys()].filter((code) => failureSpecs.has(code)));
  // A model may over-interpret a careful safety refusal as a failure.  Critical
  // caps are accepted only when the employee's own wording matches a local rule.
  const modelFailures = new Map((Array.isArray(normalized.critical_failures) ? normalized.critical_failures : []).filter((item) => failureSpecs.has(item?.code) && detectedFailureCodes.has(item.code)).map((item) => [item.code, item]));
  detectedFailureCodes.forEach((code) => { if (!modelFailures.has(code)) modelFailures.set(code, { code, evidence: detectedFailures.get(code) }); });
  const criticalFailures = [...modelFailures].map(([code, item]) => {
    const spec = failureSpecs.get(code);
    return { code, reason: item.reason || spec.rule, evidence: detectedFailures.get(code) || item.evidence || "员工原话触发了需要重点改进的规则。", score_cap: spec.score_cap };
  });
  let totalScore = dimensionScores.reduce((sum, item) => sum + item.score, 0);
  if (criticalFailures.length) totalScore = Math.min(totalScore, ...criticalFailures.map((item) => Number(item.score_cap)));
  const cleanList = (value, fallback) => Array.isArray(value) && value.filter(Boolean).length ? value.filter(Boolean).slice(0, 4) : fallback;
  const knownSceneIds = new Set((Array.isArray(scenarios) ? scenarios : []).map((item) => String(item?.id || "").trim()).filter(Boolean));
  const requestedNextScene = String(normalized.next_training_scene || "").trim();
  return sanitizeStaticAssessmentAdvice({
    total_score: totalScore,
    dimension_scores: dimensionScores,
    critical_failures: criticalFailures,
    strengths: cleanList(normalized.strengths, ["完成了本轮顾客沟通。"]),
    improvements: cleanList(normalized.improvements, ["下一轮请围绕顾客原话补齐需求分析、安全边界和可执行下一步。"]),
    next_training_scene: knownSceneIds.has(requestedNextScene) ? requestedNextScene : (Array.isArray(scenarios) ? String(scenarios[0]?.id || "") : ""),
    summary: normalized.summary || "评分已按本轮员工实际表达生成。",
  });
}

function normalizeStaticResult(result, mode, action, scenario, history, rubric, message, query = "", route = {}, scenarios = state.scenarios || []) {
  let normalized = result && typeof result === "object" ? result : {};
  if (mode === "training") {
    const fallback = staticMockProgressive(mode, action, scenario, history, rubric, message);
    normalized.customer_reply = normalizeStaticCustomerReply(normalized.customer_reply || fallback.customer_reply, scenario, history, message, true);
    normalized.feedback = normalizeStaticTrainingFeedback(normalized, scenario, history, rubric, message, normalized.customer_reply);
  }
  if (mode === "test" && action === "turn") normalized = normalizeStaticTestTurn(normalized, scenario, history, message, true);
  if (mode === "test" && action === "finish") normalized = normalizeStaticAssessment(normalized, history, rubric, scenarios);
  if (mode === "qa") normalized = normalizeStaticQaResult(normalized, message, query, route, history);
  return normalized;
}

function cleanStaticHistory(history = [], limit = 7) {
  return history.filter((item) => ["user", "assistant"].includes(item?.role) && String(item.content || "").trim()).map((item) => ({ role: item.role, content: String(item.content).trim() })).slice(-limit);
}

function staticQaNeedsDeterministicSafety(query, route = {}) {
  return route.intent_id === "INTENT-RED-FLAG"
    || route.stop_sales
    || staticPostServiceAdverseEvent(query)
    || isStaticPointWaveAftercareQuery(query)
    || /敏感肌|皮肤过敏|容易过敏|医美恢复/i.test(query)
    || /GLP-1|司美|减肥针|处方|药品|减肥药|口服片|剂量|停药|换药/i.test(query)
    || /孩子|儿童|未成年|孕妇|怀孕|备孕|哺乳|慢病|糖尿病|高血压|三高/i.test(query);
}

async function staticApi(path, body) {
  const data = await loadStaticData();
  if (path === "/api/bootstrap") {
    return { ok: true, scenarios: data.scenarios, models: AVAILABLE_MODELS, prompt_defaults: data.promptDefaults, knowledge: { rag_documents: data.documents.length, common_qa: data.commonQa.length, scenarios: data.scenarios.length }, rubric: { total: data.rubric.total, dimensions: data.rubric.dimensions || [] } };
  }
  if (path === "/api/health") return { ok: true, api_configured: Boolean(state.apiKey), mock_mode: !state.apiKey, model: state.model, models: AVAILABLE_MODELS, knowledge: { rag_documents: data.documents.length, common_qa: data.commonQa.length } };
  if (path !== "/api/chat") throw new Error("静态模式不支持该接口");

  const mode = body.mode || "qa";
  const action = body.action || "turn";
  const promptOverrides = normalizePromptOverrides(body.prompt_overrides || state.promptOverrides);
  const apiKey = body.api_key || state.apiKey;
  const model = body.model || state.model;
  if (!AVAILABLE_MODELS.some((item) => item.id === model)) throw new Error("不支持该模型，请从页面提供的模型列表中选择。");
  const scenario = data.scenarios.find((item) => item.id === body.scenario_id) || data.scenarios[0];
  const message = body.message || "";
  const history = body.history || [];
  const query = mode === "qa" ? staticQaQuery(message, history) : [...history.slice(-8).map((item) => item.content), message].join(" ");
  const trainingRetrievalQuery = mode === "training"
    ? [scenario.title || "", scenario.module_title || "", staticLatestCustomerMessage(history, scenario), message].filter(Boolean).join(" ")
    : query;
  const currentResolution = mode === "qa" && staticCurrentPointWaveAftercareResolved(message, query);
  const safetyQuery = currentResolution ? message : query;
  // Keep the complete contextual question in every QA decision and model
  // prompt.  The current message alone can be a short follow-up such as
  // “副作用呢？”, which must retain the preceding named service.
  const qaAnswerQuery = mode === "qa" ? safetyQuery : message;
  const route = staticRouteCustomerQuestion(safetyQuery, data.methodology);
  if (mode === "qa" && staticQaNeedsDeterministicSafety(safetyQuery, route)) {
    const result = normalizeStaticQaResult(
      { answer: "", uncertainties: [], recommended_action: "" },
      message,
      safetyQuery,
      route,
      history,
    );
    return {
      ok: true,
      mode,
      result,
      citations: [],
      retrieved: [],
      meta: {
        mock: true,
        model,
        common_qa: false,
        attempted: false,
        candidate_count: 0,
        selection: "deterministic_safety",
      },
    };
  }
  let commonQaMatch = null;
  let commonQaSelectionMeta = { attempted: false, candidate_count: 0 };
  if (mode === "qa") {
    const shortProjectFollowUp = /^(?:那|它|这个|这种)?(?:的)?(?:副作用|不良反应|风险|禁忌|恢复期|疼痛|红肿|肿胀|过敏|效果|适合吗?|能做吗?)(?:呢|吗|怎么样|如何|有什么|有吗)?[？?]?$/i.test(String(message).trim());
    const candidateQuery = !currentResolution && query !== message
      && (/^(?:那|这个|这种|它|刚才|如果|那么|可是|但是)/.test(String(message).trim()) || shortProjectFollowUp)
      ? query : message;
    const candidates = matchStaticCommonQaCandidates(candidateQuery, data.commonQa, 6);
    commonQaMatch = staticPointWaveBestCommonQa(candidateQuery, data.commonQa);
    if (commonQaMatch) {
      commonQaSelectionMeta = { attempted: false, candidate_count: 1, selection: "point_wave_best_answer" };
    } else {
      const selection = await selectStaticCommonQaWithModel(candidateQuery, candidates, model, apiKey);
      commonQaMatch = selection.match;
      commonQaSelectionMeta = selection.meta;
    }
  }
  let docs = commonQaMatch && mode === "qa" ? [staticCommonQaDocument(commonQaMatch)] : staticRetrieve(trainingRetrievalQuery, data.documents, 8, route, mode !== "qa");
  // Keep interactive prompts compact so multi-turn responses remain reliable
  // on the static Pages build while retrieval/citations stay unchanged.
  const context = docs.slice(0, mode === "training" ? 4 : 8).map((item) => `${item.metadata?.title || item.document_id}\n${String(item.text || "").slice(0, mode === "training" ? 650 : 1200)}`).join("\n\n");
  if (!apiKey) {
    if (mode === "qa" && commonQaMatch) {
      const result = normalizeStaticQaResult({
        answer: staticFaqCustomerVoiceFallback(commonQaMatch),
        uncertainties: [],
        recommended_action: "如需继续了解，我可以继续按当前已核验的信息为您说明；涉及动态信息或个体适用性时，请再核对有效版本。",
        faq_match: publicStaticCommonQaMatch(commonQaMatch),
        faq_controlled_answer: true,
      }, message, safetyQuery, route, history);
      if (!isStaticPointWaveAftercareQuery(safetyQuery) && !route.stop_sales) result.faq_match = publicStaticCommonQaMatch(commonQaMatch);
      else delete result.faq_match;
      const faqReference = staticCommonQaCourseReference(commonQaMatch.row);
      const references = uniqueStaticReferences([faqReference].filter(Boolean));
      return { ok: true, mode, result, citations: references, retrieved: references, meta: { mock: !commonQaSelectionMeta.attempted, model, common_qa: true, ...commonQaSelectionMeta } };
    }
    const rawResult = mode === "qa" ? staticKnowledgeQaResponse(qaAnswerQuery, route, docs) : staticMockProgressive(mode, action, scenario, history, data.rubric, message);
    const result = normalizeStaticResult(rawResult, mode, action, scenario, history, data.rubric, message, safetyQuery, route, data.scenarios);
    return { ok: true, mode, result, citations: mode === "qa" ? docs.slice(0, 3).map(publicStaticDocument) : [], retrieved: mode === "qa" ? docs.map(publicStaticDocument) : [], meta: { mock: true, model } };
  }

  const dialogue = cleanStaticHistory(history);
  const turnNumber = dialogue.filter((item) => item.role === "user").length + 1;
  const safety = "不得诊断疾病、承诺治愈或固定效果、推荐药品剂量或停药；遇到红旗症状时优先停止项目并建议医疗评估。";
  const routeContext = staticRouteContext(route);
  if (mode === "training") {
    // The customer and coach have intentionally different information
    // boundaries.  In particular, the coach request is created before and
    // independently of this turn's customer reply, so feedback used by
    // "修改这次回答" can never depend on a future disclosure.
    const customerSystem = `${promptSystemEnvelope("training_customer", promptOverrides.training.customer)}\n\n隐藏场景（不得整段泄露）：${JSON.stringify(staticCustomerScenario(scenario, true))}\n公开开场白：${scenario.opening || ""}\n对话模式：自由发挥。场景设定只帮助保持人物身份，不按隐藏信息或规则安排固定台词；请根据消息列表最后一条员工原话自然回应。\n当前是员工第 ${turnNumber} 轮回复。`;
    const coachSystem = `${promptSystemEnvelope("training_coach", promptOverrides.training.coach)}\n\n公开场景：${JSON.stringify(staticPublicTrainingScenario(scenario))}\n当前是员工第 ${turnNumber} 轮回复。history 中 role=user 是员工，role=assistant 是本轮前顾客已经说出的公开信息。\n方法路由：\n${routeContext}\n相关知识库：\n${context}`;
    const trainingMessages = [...dialogue, { role: "user", content: message }];
    const [customerSettled, coachSettled] = await Promise.allSettled([
      callStaticModel(customerSystem, trainingMessages, model, apiKey, 0.55, 500, 45000),
      callStaticModel(coachSystem, trainingMessages, model, apiKey, 0.2, 950, 45000),
    ]);
    const customerModelResult = customerSettled.status === "fulfilled" ? customerSettled.value : null;
    const coachModelResult = coachSettled.status === "fulfilled" ? coachSettled.value : null;
    if (!customerModelResult && !coachModelResult) {
      throw new Error("模拟顾客与训练教练均未返回可用结果，请稍后重试。");
    }
    const localFallback = staticMockProgressive("training", "turn", scenario, history, data.rubric, message);
    const customerContent = customerModelResult?.content || "";
    const coachContent = coachModelResult?.content || "";
    const customerPayload = customerModelResult
      ? (extractStaticJson(customerContent) || { customer_reply: customerContent })
      : { customer_reply: localFallback.customer_reply };
    const coachPayload = coachModelResult
      ? (extractStaticJson(coachContent) || {})
      : { feedback: localFallback.feedback };
    let result = {
      customer_reply: customerPayload.customer_reply || customerPayload.reply || customerContent,
      feedback: coachPayload.feedback && typeof coachPayload.feedback === "object" ? coachPayload.feedback : coachPayload,
    };
    result = normalizeStaticResult(result, mode, action, scenario, history, data.rubric, message, safetyQuery, route, data.scenarios);
    const customerUsage = customerModelResult?.meta?.usage || {};
    const coachUsage = coachModelResult?.meta?.usage || {};
    const usage = {};
    new Set([...Object.keys(customerUsage), ...Object.keys(coachUsage)]).forEach((key) => {
      const customerValue = Number(customerUsage[key]);
      const coachValue = Number(coachUsage[key]);
      if (Number.isFinite(customerValue) || Number.isFinite(coachValue)) usage[key] = (Number.isFinite(customerValue) ? customerValue : 0) + (Number.isFinite(coachValue) ? coachValue : 0);
    });
    return {
      ok: true,
      mode,
      result,
      citations: [],
      retrieved: [],
      meta: {
        model: coachModelResult?.meta?.model || customerModelResult?.meta?.model || model,
        usage,
        mock: false,
        calls: 2,
        roles: ["customer", "coach"],
        degraded: !customerModelResult || !coachModelResult,
        fallback_roles: [
          ...(!customerModelResult ? ["customer"] : []),
          ...(!coachModelResult ? ["coach"] : []),
        ],
      },
    };
  }
  let system;
  let messages;
  let temperature = 0.3;
  let maxTokens = 1800;
  if (mode === "test" && action === "turn") {
    system = `你只扮演实战考核中的模拟顾客，不是教练、客服助手或评分员。\n隐藏场景（不得泄露）：${JSON.stringify(staticCustomerScenario(scenario))}\n${LIMITED_CUSTOMER_POLICY}\n开场白已经展示，当前是员工第 ${turnNumber} 轮回复。只回应员工最新一句；绝不重复开场或原样重复旧回复；每轮最多透露一个员工问到的新背景或异议。不得出现考核、评分、知识库、方法路由、隐藏异议、must_test、员工应该等幕后词。\n回答相关性契约（优先于普通顾虑推进）：先判断员工是在提问、解释、确认还是安排下一步；第一句话必须承接同一个主题，不能突然跳到价格、项目原理或另一个顾虑。员工一句话中有多个明确问题时，按原顺序逐项回应；已回答的事实不重复，尚未掌握的内容明确说“我没留意/不太清楚”，不能只回答一个问题后换话题。员工解释数据或效果时，先回应这段解释，再提出一个与当前主题直接相关的顾虑；没有新问题时，不得凭空开启新的异议。员工给出具体方案、时间、记录方式或下一步安排时，先确认听懂、接受、犹豫或追问一个具体细节，不能只说“这些专业的我不懂”并退回旧顾虑。若员工刚解释“测量时间、条件或结果不同”，必须先回应测量安排，再提出判断周期问题。顾客可以继续提问，但必须遵循“先回应、后追问”：先用一句话确认理解、接受、犹豫或具体不清楚之处，再提出最多一个与员工刚才内容直接相关的问题，禁止跳过回应直接抛出新问题。每轮自检：回复中至少有一个短语对应员工最新问题或动作；否则改写为“我还没听明白，您刚才问的是……对吗？”这类澄清。\n严格输出 JSON：{"reply":"顾客下一句话","emotion":"curious|hesitant|concerned|relieved|neutral","should_continue":true}。`;
    system = promptSystemEnvelope("simulation_customer", promptOverrides.simulation.customer) + `\n\n场景设定（只供你使用，不得泄露）：${JSON.stringify(staticCustomerScenario(scenario, true))}\n开场白：${scenario.opening || ""}\n对话模式：自由发挥，只依据人物基础设定和消息列表最后一条员工原话回应，不按隐藏信息或规则机械释放台词。\n当前是员工第 ${turnNumber} 轮回复。`;
    messages = [...dialogue, { role: "user", content: message }];
    temperature = 0.55;
  } else if (mode === "test" && action === "finish") {
    system = promptSystemEnvelope("simulation_assessment", promptOverrides.simulation.assessment);
    messages = [{ role: "user", content: `评分表：${JSON.stringify(data.rubric)}\n公开场景：${JSON.stringify(staticPublicTrainingScenario(scenario))}\n员工完整对话：${JSON.stringify(cleanStaticHistory(body.history || [], 40))}` }];
    temperature = 0.1;
    maxTokens = 1800;
  } else {
    system = `你是企业知识库中的顾客接待助手。只基于给定的方法路由和资料直接回答顾客当前问题。${safety}\n这是连续对话，必须结合最近问题和上一轮回答理解“这个、那、它、怎么办”等指代，但只回答当前这一问，不要机械重复上一轮。先承接问题，只补一个必要信息，再给已核验内容、边界和一个可执行下一步。严格输出 JSON：{"answer":"...","uncertainties":[],"recommended_action":"..."}。`;
    system = promptSystemEnvelope("qa", promptOverrides.qa);
    messages = [...dialogue, { role: "user", content: `顾客本轮问题：${message}\n结合上下文后的当前问题：${qaAnswerQuery}\n方法路由：\n${routeContext}\n相关知识库：\n${context}` }];
  }
  const timeoutMs = mode === "test" && action === "finish" ? 60000 : 45000;
  const modelResult = await callStaticModel(system, messages, model, apiKey, temperature, maxTokens, timeoutMs);
  let result = extractStaticJson(modelResult.content) || (mode === "test" && action === "turn" ? { reply: modelResult.content, emotion: "neutral", should_continue: true } : { answer: modelResult.content, uncertainties: [], recommended_action: "" });
  result = normalizeStaticResult(result, mode, action, scenario, history, data.rubric, message, safetyQuery, route, data.scenarios);
  if (mode === "qa" && commonQaMatch) {
    if (staticFaqAnswerNeedsCustomerVoiceRepair(result.answer)) result.answer = staticFaqCustomerVoiceFallback(commonQaMatch);
    if (!isStaticPointWaveAftercareQuery(safetyQuery) && !route.stop_sales) result.faq_match = publicStaticCommonQaMatch(commonQaMatch);
    else delete result.faq_match;
    const faqReference = staticCommonQaCourseReference(commonQaMatch.row);
    const references = uniqueStaticReferences([faqReference].filter(Boolean));
    return { ok: true, mode, result, citations: references, retrieved: references, meta: { ...modelResult.meta, mock: false, common_qa: true, ...commonQaSelectionMeta } };
  }
  return { ok: true, mode, result, citations: mode === "qa" ? docs.slice(0, 3).map(publicStaticDocument) : [], retrieved: mode === "qa" ? docs.map(publicStaticDocument) : [], meta: { ...modelResult.meta, mock: false } };
}

async function api(path, body) {
  if (STATIC_PAGES) return staticApi(path, body);
  const response = await fetch(path, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : undefined);
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || "请求失败");
  return data;
}

const VOICE_SAMPLE_RATE = 16000;
const VOICE_MAX_DURATION_SECONDS = 30;

function voiceCaptureSupported() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  return Boolean(window.isSecureContext && window.navigator?.mediaDevices?.getUserMedia && AudioContextClass);
}

function voiceInputUnavailableMessage() {
  if (STATIC_PAGES) return "语音输入需要接入受保护的应用后端；当前静态页面不保存或使用讯飞凭据。";
  if (!window.isSecureContext) return "语音输入需要通过 HTTPS 打开网站（本机 localhost 也可以）。";
  return "当前浏览器不支持麦克风录音，请使用最新版 Chrome、Edge 或 Safari。";
}

function updateVoiceInputUi(phase = "idle") {
  const button = els.voiceInput;
  if (!button) return;
  const unavailable = STATIC_PAGES || !voiceCaptureSupported();
  const disabled = unavailable || state.busy || state.ended || phase === "transcribing";
  button.disabled = disabled;
  button.classList.toggle("is-recording", phase === "recording");
  button.classList.toggle("is-transcribing", phase === "transcribing");
  button.setAttribute("aria-pressed", phase === "recording" ? "true" : "false");
  if (els.voiceInputLabel) {
    els.voiceInputLabel.textContent = phase === "recording" ? "停止录音" : phase === "transcribing" ? "识别中" : "语音输入";
  }
  button.title = unavailable ? voiceInputUnavailableMessage() : phase === "recording"
    ? "正在录音，再次点击即可结束"
    : phase === "transcribing" ? "正在识别语音"
      : `语音输入：录音后转写到输入框（最长 ${VOICE_MAX_DURATION_SECONDS} 秒）`;
}

function mergeVoiceSamples(chunks) {
  const samples = (Array.isArray(chunks) ? chunks : []).filter((item) => item instanceof Float32Array);
  const size = samples.reduce((total, item) => total + item.length, 0);
  const merged = new Float32Array(size);
  let offset = 0;
  samples.forEach((item) => {
    merged.set(item, offset);
    offset += item.length;
  });
  return merged;
}

function resampleFloat32ToPcm16(samples, sourceRate, targetRate = VOICE_SAMPLE_RATE) {
  if (!(samples instanceof Float32Array) || !samples.length) return new Int16Array(0);
  if (!Number.isFinite(sourceRate) || sourceRate < 8000 || !Number.isFinite(targetRate) || targetRate < 8000) {
    throw new Error("录音采样率无效，请重新开始录音。");
  }
  const outputLength = Math.max(1, Math.round(samples.length * targetRate / sourceRate));
  const output = new Int16Array(outputLength);
  const ratio = sourceRate / targetRate;
  for (let index = 0; index < outputLength; index += 1) {
    const position = index * ratio;
    const before = Math.min(samples.length - 1, Math.floor(position));
    const after = Math.min(samples.length - 1, before + 1);
    const fraction = position - before;
    const value = Math.max(-1, Math.min(1, samples[before] * (1 - fraction) + samples[after] * fraction));
    output[index] = value < 0 ? Math.round(value * 0x8000) : Math.round(value * 0x7fff);
  }
  return output;
}

function pcm16ToBase64(samples) {
  if (!(samples instanceof Int16Array) || !samples.length) throw new Error("没有录到可识别的语音。");
  const bytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, Math.min(bytes.length, offset + chunkSize)));
  }
  return window.btoa(binary);
}

function disposeVoiceCapture(capture) {
  if (!capture) return;
  clearTimeout(capture.limitTimer);
  try { capture.processor.disconnect(); } catch (_error) { /* already disconnected */ }
  try { capture.source.disconnect(); } catch (_error) { /* already disconnected */ }
  try { capture.silent.disconnect(); } catch (_error) { /* already disconnected */ }
  capture.stream.getTracks().forEach((track) => track.stop());
  Promise.resolve(capture.audioContext.close()).catch(() => {});
}

function appendVoiceTranscript(text) {
  const transcript = String(text || "").trim();
  if (!transcript) return;
  const existing = els.input.value.trim();
  els.input.value = existing ? `${existing}${/[。！？!?，,；;]$/.test(existing) ? "" : "，"}${transcript}` : transcript;
  els.input.focus();
  els.input.setSelectionRange(els.input.value.length, els.input.value.length);
}

async function stopVoiceInput({ transcribe = true } = {}) {
  const capture = state.voiceCapture;
  if (!capture) return;
  state.voiceCapture = null;
  disposeVoiceCapture(capture);
  if (!transcribe) {
    updateVoiceInputUi();
    return;
  }
  const requestId = capture.requestId;
  let pcm;
  try {
    pcm = resampleFloat32ToPcm16(mergeVoiceSamples(capture.chunks), capture.sampleRate);
  } catch (error) {
    if (requestId === state.voiceRequestSerial) showToast(error.message || "录音处理失败，请再试一次。", true);
    updateVoiceInputUi();
    return;
  }
  if (!pcm.length) {
    if (requestId === state.voiceRequestSerial) showToast("没有录到清晰语音，请靠近麦克风后再试。", true);
    updateVoiceInputUi();
    return;
  }
  updateVoiceInputUi("transcribing");
  try {
    const data = await api("/api/asr", { audio_base64: pcm16ToBase64(pcm), sample_rate: VOICE_SAMPLE_RATE });
    if (requestId !== state.voiceRequestSerial || state.ended) return;
    appendVoiceTranscript(data.text);
    showToast("语音已转成文字，确认或修改后再发送。");
  } catch (error) {
    if (requestId === state.voiceRequestSerial) showToast(error.message || "语音识别失败，请稍后再试。", true);
  } finally {
    if (requestId === state.voiceRequestSerial) updateVoiceInputUi();
  }
}

async function startVoiceInput() {
  if (state.voiceCapture) {
    await stopVoiceInput();
    return;
  }
  if (state.busy || state.ended) return;
  if (STATIC_PAGES || !voiceCaptureSupported()) {
    showToast(voiceInputUnavailableMessage(), true);
    return;
  }
  const requestId = ++state.voiceRequestSerial;
  let stream;
  let audioContext;
  let source;
  let processor;
  let silent;
  try {
    stream = await window.navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    audioContext = new AudioContextClass();
    await audioContext.resume();
    source = audioContext.createMediaStreamSource(stream);
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    silent = audioContext.createGain();
    silent.gain.value = 0;
    const capture = {
      requestId,
      stream,
      audioContext,
      source,
      processor,
      silent,
      sampleRate: audioContext.sampleRate,
      chunks: [],
      limitTimer: 0,
    };
    processor.onaudioprocess = (event) => capture.chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
    source.connect(processor);
    processor.connect(silent);
    silent.connect(audioContext.destination);
    if (requestId !== state.voiceRequestSerial || state.ended) {
      disposeVoiceCapture(capture);
      return;
    }
    capture.limitTimer = window.setTimeout(() => {
      if (state.voiceCapture?.requestId === requestId) {
        showToast(`已达到 ${VOICE_MAX_DURATION_SECONDS} 秒录音上限，正在识别。`);
        void stopVoiceInput();
      }
    }, VOICE_MAX_DURATION_SECONDS * 1000);
    state.voiceCapture = capture;
    updateVoiceInputUi("recording");
    showToast(`正在录音，再次点击结束（最长 ${VOICE_MAX_DURATION_SECONDS} 秒）。`);
  } catch (error) {
    if (processor && source && silent && stream && audioContext) {
      disposeVoiceCapture({ processor, source, silent, stream, audioContext, limitTimer: 0 });
    } else {
      stream?.getTracks().forEach((track) => track.stop());
      Promise.resolve(audioContext?.close()).catch(() => {});
    }
    if (requestId === state.voiceRequestSerial) {
      const denied = error?.name === "NotAllowedError" || error?.name === "SecurityError";
      showToast(denied ? "未获得麦克风权限，请在浏览器中允许后再试。" : "无法启动录音，请检查麦克风后再试。", true);
      updateVoiceInputUi();
    }
  }
}

function cancelVoiceInput() {
  state.voiceRequestSerial += 1;
  void stopVoiceInput({ transcribe: false });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);
}

function showToast(message, error = false) {
  els.toast.textContent = message;
  els.toast.classList.toggle("error", error);
  els.toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => els.toast.classList.add("hidden"), 3600);
}

function moduleById(moduleId) {
  return state.modules.find((module) => module.id === moduleId) || state.modules[0] || null;
}

function exactModuleById(moduleId) {
  return state.modules.find((module) => module.id === moduleId) || null;
}

function realExamById(examId) {
  return state.realExamBank?.exams?.find((exam) => exam.id === examId) || null;
}

function routeItemById(route, itemId) {
  if (!itemId) return null;
  if (route === "exam/objective") return exactModuleById(itemId) || realExamById(itemId);
  return exactModuleById(itemId);
}

function isRealExam(exam) {
  return Boolean(exam && Array.isArray(exam.questions));
}

function activeModuleId() {
  if (state.route === "learning/course") return state.learningModuleId;
  if (state.route === "learning/practice") return state.practiceModuleId;
  if (state.route === "exam/objective") return state.objectiveModuleId;
  if (state.route === "exam/simulation") return state.simulationModuleId;
  return null;
}

function activeModule() {
  return moduleById(activeModuleId());
}

function moduleCourses(moduleId) {
  return state.courses.filter((course) => course.module_id === moduleId).sort((a, b) => a.order - b.order);
}

function moduleGroups(moduleId) {
  return state.catalogIndex.find((item) => item.module_id === moduleId)?.groups || [];
}

const COURSE_DOMAIN_MODULES = {
  onboarding: "MOD-01", company: "MOD-01", reception: "MOD-02", sales_skills: "MOD-02",
  point_wave: "MOD-03", point_wave_ops: "MOD-03", professional_qa: "MOD-03", training_video: "MOD-03",
  super_v: "MOD-04", point_wave_super_v: "MOD-04",
  beauty: "MOD-08", beauty_ops: "MOD-08",
  slimming: "MOD-05", slimming_reception: "MOD-05", slimming_product: "MOD-05", slimming_science: "MOD-05",
  objections: "MOD-02", comparison: "MOD-02",
  safety: "MOD-01", service_safety: "MOD-01", operations: "MOD-01", product_ops: "MOD-01",
};

const COMMON_QA_COURSE_FALLBACKS = {
  "COURSE-FAQ-POINT-WAVE-001": "COURSE-MOD-03-02",
  "COURSE-FAQ-SUPER-V-001": "COURSE-MOD-04-02",
  "COURSE-FAQ-SLIMMING-001": "COURSE-MOD-05-03",
  "COURSE-FAQ-OBJECTION-001": "COURSE-MOD-02-04",
  "COURSE-FAQ-SAFETY-001": "COURSE-MOD-06-02",
  "COURSE-FAQ-BEAUTY-001": "COURSE-MOD-09-03",
};

const courseSearchTermCache = new Map();

function searchableTerms(value) {
  const text = String(value || "").toLowerCase();
  const terms = new Set(text.match(/[a-z0-9_]{2,}|[\u4e00-\u9fff]/gi) || []);
  for (let index = 0; index < text.length - 1; index += 1) {
    const pair = text.slice(index, index + 2);
    if (/^[\u4e00-\u9fff]{2}$/.test(pair)) terms.add(pair);
  }
  return terms;
}

function courseSearchTerms(course) {
  if (!courseSearchTermCache.has(course.id)) {
    courseSearchTermCache.set(course.id, searchableTerms(JSON.stringify(course)));
  }
  return courseSearchTermCache.get(course.id);
}

function bestReferenceCourse(candidates, reference) {
  if (!candidates.length) return null;
  if (candidates.length === 1) return candidates[0];
  const metadata = reference.metadata || {};
  const referenceTerms = searchableTerms(`${metadata.title || ""} ${metadata.section_title || ""} ${reference.title || ""} ${reference.text || ""}`);
  return candidates.reduce((best, course) => {
    const score = [...referenceTerms].reduce((total, term) => total + (courseSearchTerms(course).has(term) ? 1 : 0), 0);
    return !best || score > best.score ? { course, score } : best;
  }, null)?.course || candidates[0];
}

function resolveReferenceCourse(reference = {}) {
  const metadata = reference.metadata || {};
  const requestedId = reference.course_id || metadata.course_id;
  if (requestedId) {
    const direct = state.courses.find((course) => course.id === requestedId)
      || state.courses.find((course) => course.id === COMMON_QA_COURSE_FALLBACKS[requestedId]);
    if (direct) return direct;
  }

  const documentId = String(reference.document_id || "");
  const documentCourseId = documentId.startsWith("COURSE-")
    ? documentId.replace(/-SECTION-\d+$/, "")
    : documentId ? `COURSE-${documentId}` : "";
  if (documentCourseId) {
    const direct = state.courses.find((course) => course.id === documentCourseId);
    if (direct) return direct;
  }

  const title = String(reference.title || metadata.title || "").trim();
  const titleMatch = state.courses.find((course) => course.title === title);
  if (titleMatch) return titleMatch;

  const sourceIds = new Set([
    ...(Array.isArray(reference.source_ids) ? reference.source_ids : []),
    ...(Array.isArray(metadata.source_ids) ? metadata.source_ids : []),
    ...String(reference.source_id || metadata.source_id || "").split(","),
  ].map((item) => String(item).trim()).filter(Boolean));
  if (sourceIds.size) {
    const sourceMatches = state.courses.filter((course) => (course.source_ids || []).some((sourceId) => sourceIds.has(sourceId)));
    if (sourceMatches.length) return bestReferenceCourse(sourceMatches, reference);
  }

  const moduleId = metadata.module_id || COURSE_DOMAIN_MODULES[metadata.domain] || COURSE_DOMAIN_MODULES[reference.domain];
  if (moduleId) return bestReferenceCourse(state.courses.filter((course) => course.module_id === moduleId), reference);
  return null;
}

function routePath(route = state.route, moduleId = state.routeModuleId) {
  return `#${route}${moduleId ? `/${moduleId}` : ""}`;
}

function parseRouteHash(hash = window.location.hash) {
  let raw;
  try {
    raw = decodeURIComponent(String(hash || "").replace(/^#/, "")).replace(/^\/+|\/+$/g, "");
  } catch {
    return { route: "learning", moduleId: null, invalid: true };
  }
  raw = LEGACY_ROUTES[raw] || raw || "learning";
  if (VALID_ROUTES.has(raw)) return { route: raw, moduleId: null, invalid: false };
  const activity = [...VALID_ROUTES]
    .filter((route) => ROUTE_CONFIG[route].screen === "activity")
    .sort((a, b) => b.length - a.length)
    .find((route) => raw.startsWith(`${route}/`));
  if (!activity) return { route: "learning", moduleId: null, invalid: true };
  const moduleId = raw.slice(activity.length + 1);
  if (!routeItemById(activity, moduleId)) return { route: activity, moduleId: null, invalid: true };
  return { route: activity, moduleId, invalid: false };
}

function activityModuleStats(route, module) {
  if (route === "learning/course") {
    return `${moduleGroups(module.id).length} 个章节 · ${moduleCourses(module.id).length} 节课程`;
  }
  if (route === "exam/objective") {
    const exam = objectiveExamById(module.id);
    return `${examQuestions(exam).length} 道题${isRealExam(exam) ? ` · 满分 ${examTotalPoints(exam)} 分` : ""}`;
  }
  return `${moduleScenarios(module.id).length} 个顾客场景`;
}

function renderModuleGateway() {
  const config = ROUTE_CONFIG[state.route];
  els.gatewayTag.textContent = config.tag;
  els.gatewayTitle.textContent = config.gatewayTitle || `选择${config.title}模块`;
  els.gatewayDescription.textContent = config.description;
  els.gatewayBack.dataset.route = config.parent;
  const moduleCards = state.modules.map((module) => `
    <button class="module-route-card" data-module-id="${escapeHtml(module.id)}">
      <span>模块 ${String(module.order).padStart(2, "0")}</span>
      <h3>${escapeHtml(module.title)}</h3>
      <p>${escapeHtml(activityModuleStats(state.route, module))}</p>
      <b>${escapeHtml(config.action)} →</b>
    </button>`).join("");
  const realExams = state.route === "exam/objective" ? state.realExamBank?.exams || [] : [];
  if (!realExams.length) {
    els.moduleRouteGrid.classList.remove("grouped");
    els.moduleRouteGrid.innerHTML = moduleCards;
    return;
  }
  const realExamCards = realExams.map((exam, index) => `
    <button class="module-route-card real-exam-card" data-module-id="${escapeHtml(exam.id)}">
      <span>真实考试 ${String(index + 1).padStart(2, "0")}</span>
      <h3>${escapeHtml(exam.title)}</h3>
      <p>${examQuestions(exam).length} 道题 · 满分 ${examTotalPoints(exam)} 分</p>
      <b>进入考试 →</b>
    </button>`).join("");
  els.moduleRouteGrid.classList.add("grouped");
  els.moduleRouteGrid.innerHTML = `
    <section class="module-route-group">
      <div class="module-route-group-head"><div><span>知识模块测试</span><h3>按知识模块巩固学习成果</h3></div><b>${state.modules.length} 个模块</b></div>
      <div class="module-route-list">${moduleCards}</div>
    </section>
    <section class="module-route-group real-exam-group">
      <div class="module-route-group-head"><div><span>真实考试</span><h3>按原试卷完成正式答题</h3></div><b>${realExams.length} 套试卷</b></div>
      <p class="real-exam-note">填空题由系统判分；问答题提交后显示原卷答案，由监考人按题目分值录入得分。</p>
      <div class="module-route-list">${realExamCards}</div>
    </section>`;
}

function conversationCopy() {
  if (state.route === "exam/simulation") {
    return {
      kicker: "模拟顾客考核",
      conversation: "独立接待模拟顾客",
      hint: "至少完成 4 轮对话后可结束考核",
      placeholder: "输入你准备对顾客说的话…",
      finish: "完成考核并查看结果",
    };
  }
  const copy = modeCopy[state.mode];
  return {
    kicker: copy.kicker,
    conversation: copy.conversation,
    hint: copy.hint,
    placeholder: state.mode === "qa" ? "输入顾客的问题，例如：做一次就一定有效吗？" : "输入你准备对顾客说的话…",
    finish: "结束陪练并查看报告",
  };
}

function renderRoute() {
  const config = ROUTE_CONFIG[state.route] || ROUTE_CONFIG.learning;
  const workspace = config.screen === "workspace" || (config.screen === "activity" && Boolean(state.routeModuleId));
  const gateway = config.screen === "activity" && !state.routeModuleId;
  const routeItem = workspace && state.routeModuleId ? routeItemById(state.route, state.routeModuleId) : null;
  const realObjectiveExam = state.route === "exam/objective" && isRealExam(routeItem);
  const moduleObjectiveExam = state.route === "exam/objective" && !realObjectiveExam
    ? objectiveExamById(state.routeModuleId)
    : null;
  state.mode = config.mode;
  els.modeButtons.forEach((button) => button.classList.toggle("active", button.dataset.route === config.area));
  els.modeBreadcrumb.textContent = config.nav;
  els.pageTitle.textContent = routeItem?.title || config.title;
  els.pageDescription.textContent = realObjectiveExam
    ? `完成 ${examQuestions(routeItem).length} 道正式试题，提交后按原卷答案批阅并查看成绩。`
    : moduleObjectiveExam
      ? `完成本模块 ${examQuestions(moduleObjectiveExam).length} 道题，交卷后查看成绩和解析。`
    : workspace && state.routeModuleId ? config.workspaceDescription || config.description : config.pageDescription || config.description;
  els.learningHubPage.classList.toggle("hidden", state.route !== "learning");
  els.assessmentHubPage.classList.toggle("hidden", state.route !== "exam");
  els.moduleGatewayPage.classList.toggle("hidden", !gateway);
  els.learningPage.classList.toggle("hidden", !(state.route === "learning/course" && workspace));
  els.trainingPage.classList.toggle("hidden", !(state.route === "learning/practice" && workspace));
  els.testPage.classList.toggle("hidden", !(["exam/objective", "exam/simulation"].includes(state.route) && workspace));
  els.qaPage.classList.toggle("hidden", state.route !== "qa");
  const showConversation = state.route === "qa" || ((state.route === "learning/practice" || state.route === "exam/simulation") && workspace);
  els.conversationStage.classList.toggle("hidden", !showConversation);
  els.finish.classList.toggle("hidden", state.route === "qa");
  const conversation = conversationCopy();
  els.conversationAvatar.textContent = state.mode === "qa" ? "AI" : "客";
  els.conversationKicker.textContent = conversation.kicker;
  els.conversationTitle.textContent = conversation.conversation;
  els.composerHint.textContent = conversation.hint;
  els.input.placeholder = conversation.placeholder;
  if (els.clearChat) els.clearChat.textContent = state.route === "qa" ? "新对话" : state.route === "exam/simulation" ? "重新考核" : "重新练习";
  if (!state.ended) els.finish.textContent = conversation.finish;
  if (gateway) renderModuleGateway();
  if (state.route === "exam/objective" && workspace) {
    const exam = activeExamModule();
    const realExam = isRealExam(exam);
    els.testRouteBack.dataset.route = "exam/objective";
    els.testRouteTag.textContent = realExam ? "真实考试" : "知识考试";
    els.testRouteTitle.textContent = realExam ? exam.title : "模块知识考试";
    els.testRouteDescription.textContent = realExam
      ? `完成全部 ${examQuestions(exam).length} 题后提交；填空题自动判分，问答题按原卷答案批阅。`
      : `完成全部 ${examQuestions(exam).length} 题后交卷，即可查看成绩、答案和解析。`;
  } else if (state.route === "exam/simulation" && workspace) {
    els.testRouteBack.dataset.route = "exam/simulation";
    els.testRouteTag.textContent = "实战对话";
    els.testRouteTitle.textContent = "模拟顾客考核";
    els.testRouteDescription.textContent = "请像真实接待一样完成至少 4 轮对话，结束后查看评分和改进建议。";
  }
}

function renderModuleOptions() {
  const options = state.modules.map((module) => `<option value="${module.id}">${String(module.order).padStart(2, "0")} · ${escapeHtml(module.title)}</option>`).join("");
  els.learningSelect.innerHTML = options;
  els.practiceSelect.innerHTML = options;
  els.testSelect.innerHTML = options;
  els.learningSelect.value = state.learningModuleId;
  els.practiceSelect.value = state.practiceModuleId;
  els.testSelect.value = state.route === "exam/simulation" ? state.simulationModuleId : state.objectiveModuleId;
}

function renderCourseSummary(summary) {
  const items = String(summary || "").split(/[；;]\s*/).map((item) => item.trim()).filter(Boolean);
  return items.length > 1
    ? `<ul class="course-summary-points">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : `<p>${escapeHtml(items[0] || "请根据当前课程内容学习，并以最新标准为准。")}</p>`;
}

function renderLearning() {
  const module = moduleById(state.learningModuleId);
  if (!module) return;
  const groups = moduleGroups(module.id);
  const courses = moduleCourses(module.id);
  const moduleDescription = String(module.description || "").trim();
  els.learningSummary.innerHTML = `
    <div><span>正在学习</span><h3>${escapeHtml(module.title)}</h3>${moduleDescription && moduleDescription !== module.title ? `<p>${escapeHtml(moduleDescription)}</p>` : ""}</div>
    <div class="summary-count"><strong>${groups.length}</strong><span>个章节</span><strong>${courses.length}</strong><span>节课程</span></div>`;
  els.learningChapters.innerHTML = groups.map((group, index) => {
    // Prefer the stable group id, but fall back to the catalog's explicit course_ids.
    // This keeps the learning page usable when a refreshed catalog changes group labels.
    const groupCourseIds = new Set(Array.isArray(group.course_ids) ? group.course_ids : []);
    const groupCourses = courses.filter((course) => course.group_id === group.group_id || groupCourseIds.has(course.id));
    const groupDescription = String(group.description || "").trim();
    return `<article class="chapter-card">
      <div class="chapter-head"><div class="chapter-number">${String(index + 1).padStart(2, "0")}</div><div><h3>${escapeHtml(group.title)}</h3>${groupDescription && groupDescription !== group.title ? `<p>${escapeHtml(groupDescription)}</p>` : ""}</div><span>${groupCourses.length} 节</span></div>
      <div class="chapter-courses">${groupCourses.map((course) => `
        <button class="course-preview" data-course-id="${escapeHtml(course.id)}" data-course-title="${escapeHtml(course.title)}">
          <span class="course-type">${course.kind === "objection" ? "接待案例" : "专业课程"} · ${course.estimated_minutes} 分钟</span>
          <strong>${escapeHtml(course.title)}</strong>${renderCourseSummary(course.summary)}<i>打开课程 →</i>
        </button>`).join("")}</div>
    </article>`;
  }).join("");
  bindCourseButtons(els.learningChapters);
}

function renderLearningValue(value) {
  if (Array.isArray(value)) {
    if (value.every((item) => item && typeof item === "object" && "label" in item)) {
      return `<div class="learning-kv">${value.map((item) => `<div class="learning-kv-row"><b>${escapeHtml(item.label)}</b>${renderLearningValue(item.content)}</div>`).join("")}</div>`;
    }
    return `<ul class="course-points">${value.map((item) => `<li>${typeof item === "object" ? renderLearningValue(item) : escapeHtml(item)}</li>`).join("")}</ul>`;
  }
  if (value && typeof value === "object") {
    const imageKeys = new Set(["image_url", "image_alt", "secondary_image_url", "secondary_image_alt"]);
    const entries = Object.entries(value).filter(([key]) => !imageKeys.has(key));
    const figures = [
      value.image_url ? { url: value.image_url, alt: value.image_alt || "课程操作示意图" } : null,
      value.secondary_image_url ? { url: value.secondary_image_url, alt: value.secondary_image_alt || "课程操作示意图" } : null,
    ].filter(Boolean);
    return `${entries.length ? `<div class="learning-kv">${entries.map(([key, item]) => `<div class="learning-kv-row"><b>${escapeHtml(key)}</b>${renderLearningValue(item)}</div>`).join("")}</div>` : ""}${figures.length ? `<div class="course-figures">${figures.map((figure) => `<figure><img src="${escapeHtml(figure.url)}" alt="${escapeHtml(figure.alt)}" loading="lazy"><figcaption>${escapeHtml(figure.alt)}</figcaption></figure>`).join("")}</div>` : ""}`;
  }
  return `<p>${escapeHtml(value)}</p>`;
}

function resetCourseModalScroll() {
  const backdrop = $("course-modal");
  [backdrop, backdrop.querySelector(".course-modal"), els.courseModalContent].forEach((container) => {
    if (!container) return;
    container.scrollTop = 0;
    container.scrollLeft = 0;
  });
}

function openCourse(courseId, title) {
  const course = resolveReferenceCourse({ course_id: courseId, title });
  if (!course) {
    showToast("暂未找到对应课程，可先参考当前回答。", true);
    return;
  }
  resetCourseModalScroll();
  const module = moduleById(course.module_id);
  els.courseModalContent.innerHTML = `
    <div class="course-modal-breadcrumb">${escapeHtml(module?.title || "学习模块")} <span>›</span> ${escapeHtml(course.group_title || "课程")}</div>
    <div class="course-modal-header"><span>${course.kind === "objection" ? "接待案例" : "专业课程"} · 约 ${course.estimated_minutes} 分钟</span><h2 id="course-modal-title">${escapeHtml(course.title)}</h2><p>${escapeHtml(course.summary)}</p></div>
    <div class="course-sections">${course.sections.map((section) => `<section class="course-section"><h3>${escapeHtml(section.title)}</h3>${renderLearningValue(section.content)}</section>`).join("")}</div>`;
  openModal("course-modal");
  resetCourseModalScroll();
  requestAnimationFrame(resetCourseModalScroll);
}

function bindCourseButtons(root) {
  root.querySelectorAll("[data-course-id], [data-course-title]").forEach((button) => {
    button.addEventListener("click", () => openCourse(button.dataset.courseId, button.dataset.courseTitle));
  });
}

function moduleScenarios(moduleId = activeModuleId()) {
  const ids = moduleById(moduleId)?.scenario_ids || [];
  const linked = ids.map((id) => state.scenarios.find((scenario) => scenario.id === id)).filter(Boolean);
  return linked.length ? linked : state.scenarios.filter((scenario) => scenario.module_id === moduleId);
}

function selectScenario() {
  const choices = moduleScenarios();
  const selected = choices[state.scenarioIndex % Math.max(choices.length, 1)] || state.scenarios[0] || null;
  const examDetail = state.examBank?.modules?.flatMap((item) => item.scenarios || []).find((item) => item.id === selected?.id);
  state.scenario = examDetail ? { ...selected, ...examDetail } : selected;
}

function activeExamModule() {
  return objectiveExamById(state.objectiveModuleId);
}

function objectiveExamById(examId) {
  return state.examBank?.modules?.find((item) => item.id === examId) || realExamById(examId);
}

function objectiveAnswerKey(question) {
  return question.id;
}

function examQuestions(exam) {
  if (!exam) return [];
  if (isRealExam(exam)) return exam.questions.map((question) => ({
    ...question,
    type: question.type === "subjective" ? "short_answer" : question.type,
    points: Number(question.points || 0),
  }));
  return [
    ...(exam.fill_blanks || []).map((question) => ({
      ...question,
      type: "fill_blank",
      section: "填空题",
      points: 2,
      answer_parts: [{ answer: question.answers?.[0] || "", aliases: question.answers?.slice(1) || [] }],
      reference_answer: (question.answers || []).join(" / "),
    })),
    ...(exam.choices || []).map((question) => ({
      ...question,
      type: question.kind === "multiple" ? "multiple" : "single",
      section: "选择题",
      points: 4,
      reference_answer: (question.answers || []).join("、"),
    })),
    ...(exam.faq_keyword_answers || []).map((question) => ({
      ...question,
      type: "keyword_answer",
      section: "FAQ 关键词问答",
      points: Number(question.points || 0),
    })),
  ];
}

function examTotalPoints(exam) {
  return examQuestions(exam).reduce((total, question) => total + Number(question.points || 0), 0);
}

function formatPoints(value) {
  const number = Math.round(Number(value || 0) * 100) / 100;
  return Number.isInteger(number) ? String(number) : String(number.toFixed(2)).replace(/0+$/, "").replace(/\.$/, "");
}

function normalizedAnswerParts(question) {
  return (question.answer_parts || []).map((part, index) => {
    if (typeof part === "string") return { index: index + 1, answer: part, aliases: [] };
    if (Array.isArray(part)) return { index: index + 1, answer: part[0] || "", aliases: part.slice(1) };
    return { index: part.index || index + 1, answer: part.answer || "", aliases: part.aliases || [] };
  });
}

function normalizedExamText(value) {
  const text = String(value || "").normalize("NFKC").trim();
  const numericLike = /^[\d一二三四五六七八九十百千万半点.\-—–－~～至到\/\s]+$/.test(text);
  if (numericLike) {
    return text.replace(/\s/g, "").replace(/[—–－~～至]/g, "-").toLowerCase();
  }
  return text.replace(/[，、；。,.!?！？：:\s（）()《》“”"'‘’\-—_\/]/g, "").toLowerCase();
}

function answerMatches(actual, answer, aliases = []) {
  const normalized = normalizedExamText(actual);
  return [answer, ...aliases].some((candidate) => normalized === normalizedExamText(candidate));
}

const FAQ_KEYWORD_CONCEPT_TOKENS = [
  "医疗专业人员", "有资质人员", "医院冲击波", "大小便异常", "不能负重", "进行性麻木无力",
  "物理刺激", "机械刺激", "门店体验", "医学诊断", "医疗诊断", "治疗疾病", "固定效果", "固定次数", "固定时间",
  "疼痛程度", "疼痛性质", "伴随症状", "开始时间", "持续时间", "正常反应", "处理措施", "工作方式", "刺激范围",
  "医疗设备", "医疗流程", "推断效果", "同条件复测", "活动影响", "神经症状", "突发剧痛", "操作规范", "专业人员",
  "个体差异", "暂停", "停止", "坚持", "硬撑", "忍耐", "疼痛", "麻木", "无力", "放射", "负责人", "上报",
  "加重", "有效", "变化", "记录", "部位", "设置", "就医", "医疗评估", "比较", "体验", "风险", "复测",
  "按摩", "放松", "参数", "发数", "深度", "目标", "耐受", "超v", "热感", "同意", "试感", "购买",
  "诱因", "外伤", "sop", "说明书", "诊断", "手术", "植入物", "用药", "停药", "换药", "基线",
];

function normalizedKeywordText(value) {
  return String(value || "").normalize("NFKC").toLowerCase()
    .replace(/什么时候/g, "何时")
    .replace(/问清|询问|了解/g, "问")
    .replace(/解释成|解释为|当成|视为/g, "解释")
    .replace(/不可以|不能够|不可|不得|不应|不要|不用|不必|无需|无须/g, "不")
    .replace(/立即|马上/g, "")
    .replace(/当前|具体/g, "")
    .replace(/分别取得|分别确认|逐项确认/g, "分别")
    .replace(/同一个|相同|同一/g, "同")
    .replace(/只按|仅凭|单凭|凭借|凭/g, "按")
    .replace(/以及|并且|而且|和|与|也/g, "")
    .replace(/[，、；。,.!?！？：:\s（）()《》“”"'‘’\-—_\/]/g, "");
}

function keywordTermMatches(actualText, candidateText) {
  const actual = normalizedKeywordText(actualText);
  const candidate = normalizedKeywordText(candidateText);
  if (!candidate) return false;
  if (actual.includes(candidate)) return true;
  const tokens = FAQ_KEYWORD_CONCEPT_TOKENS
    .map((token) => normalizedKeywordText(token))
    .filter((token, index, all) => token && candidate.includes(token) && all.indexOf(token) === index);
  if (!tokens.length) return false;
  const candidateIsNegative = /不|禁止|避免|拒绝/.test(candidate);
  if (candidateIsNegative) {
    const hasMatchingNegation = tokens.some((token) => {
      let start = actual.indexOf(token);
      while (start >= 0) {
        if (/不|禁止|避免|拒绝/.test(actual.slice(Math.max(0, start - 5), start))) return true;
        start = actual.indexOf(token, start + token.length);
      }
      return false;
    });
    if (!hasMatchingNegation) return false;
  }
  const matched = tokens.filter((token) => actual.includes(token)).length;
  const needed = tokens.length === 1 ? 1 : Math.ceil(tokens.length * 0.6);
  return matched >= needed;
}

function keywordAnswerSafetyBlock(question, actualAnswer) {
  const answer = String(actualAnswer || "").trim();
  if (!answer) return "";

  // Keyword groups are deliberately permissive about natural-language
  // synonyms.  That must not let a learner quote the safe answer and then
  // reverse it with “but we still continue”.  Reuse the clause-aware safety
  // detector so a negated example such as “不能强迫继续” remains valid while
  // an affirmed instruction to continue, normalize pain or skip safety
  // handling always fails the entire answer.
  if (staticTrainingMessageHasUnsafeContradiction(answer)) {
    return "回答同时包含推进、弱化异常或其他危险反向指令，不能用安全关键词抵消。";
  }

  const isPointWaveSafetyQuestion = /^FAQ-M03-K0[2367]$/i.test(String(question?.id || ""));
  if (!isPointWaveSafetyQuestion) return "";

  const forcesContinuation = staticHasAffirmativeEmployeeMatch(
    answer,
    /(?:强迫|逼迫|要求).{0,8}(?:继续|坚持|忍耐)|(?:必须|务必|一定).{0,12}(?:继续|坚持|忍耐|做完)|(?:不暂停|不停止|不记录|不(?:联系|通知)负责人|不就医)/i,
  );
  const skipsSafetyScreening = staticHasAffirmativeEmployeeMatch(
    answer,
    /(?:疼痛(?:程度|性质)?|麻木|无力|伴随症状).{0,10}(?:不用|不必|无需|不需要|没必要).{0,6}(?:问|确认|记录)|(?:不用|不必|无需|不需要|没必要).{0,12}(?:问|确认|记录).{0,12}(?:疼痛(?:程度|性质)?|麻木|无力|伴随症状)/i,
  );
  if (forcesContinuation || skipsSafetyScreening) {
    return "回答明确强迫继续或跳过必要安全问询，不能判为正确。";
  }
  return "";
}

function keywordAnswerScore(question, actualAnswer) {
  const safetyBlockReason = keywordAnswerSafetyBlock(question, actualAnswer);
  const groups = (question.keyword_groups || []).map((group, index) => {
    const terms = Array.isArray(group.terms) ? group.terms.filter(Boolean) : [];
    const matchedTerms = terms.filter((term) => keywordTermMatches(actualAnswer, term));
    const labelMatched = keywordTermMatches(actualAnswer, group.label || "");
    return {
      id: String(group.id || `group-${index + 1}`),
      label: String(group.label || `关键词组 ${index + 1}`),
      required: group.required === true,
      matched: matchedTerms.length > 0 || labelMatched,
      matched_terms: matchedTerms,
    };
  });
  const matched = groups.filter((group) => group.matched);
  const requiredGroups = groups.filter((group) => group.required);
  const minimum = Math.max(1, Math.min(groups.length, Number(question.minimum_groups || groups.length || 1)));
  const requiredSatisfied = requiredGroups.every((group) => group.matched);
  const correct = !safetyBlockReason && groups.length > 0 && matched.length >= minimum && requiredSatisfied;
  const partialRatio = groups.length ? matched.length / groups.length : 0;
  const points = Number(question.points || 0);
  return {
    correct,
    earned: safetyBlockReason ? 0 : Math.round((correct ? points : points * partialRatio) * 100) / 100,
    safety_blocked: Boolean(safetyBlockReason),
    safety_block_reason: safetyBlockReason,
    matched_groups: matched.map((group) => group.label),
    missing_groups: groups.filter((group) => !group.matched).map((group) => group.label),
    required_groups: requiredGroups.map((group) => group.label),
    matched_terms: matched.flatMap((group) => group.matched_terms),
    matched_count: matched.length,
    minimum_groups: minimum,
  };
}

function questionReferenceAnswer(question) {
  if (question.reference_answer) return question.reference_answer;
  if (question.type === "fill_blank") return normalizedAnswerParts(question).map((part) => part.answer).join("；");
  return (question.answers || []).join("、");
}

function questionAnswerText(question, value) {
  if (question.type === "fill_blank") return (Array.isArray(value) ? value : [value]).map((item) => String(item || "").trim()).filter(Boolean).join("；");
  if (["single", "multiple"].includes(question.type)) return (Array.isArray(value) ? value : [value]).filter(Boolean).join("、");
  return String(value || "").trim();
}

function questionIsAnswered(question, value) {
  if (question.type === "fill_blank") {
    const parts = normalizedAnswerParts(question);
    const values = Array.isArray(value) ? value : [value];
    return parts.length > 0 && parts.every((part, index) => String(values[index] || "").trim());
  }
  if (["single", "multiple"].includes(question.type)) return Array.isArray(value) && value.length > 0;
  return Boolean(String(value || "").trim());
}

function examSectionGroups(questions) {
  const groups = [];
  questions.forEach((question) => {
    const title = question.section || (question.type === "short_answer" ? "问答题" : "考试题");
    let group = groups.find((item) => item.title === title);
    if (!group) {
      group = { title, questions: [] };
      groups.push(group);
    }
    group.questions.push(question);
  });
  return groups;
}

function objectiveAnswers(moduleId = state.objectiveModuleId) {
  if (!moduleId) return {};
  state.objectiveAnswersByModule[moduleId] ||= {};
  return state.objectiveAnswersByModule[moduleId];
}

function objectiveScore(moduleId = state.objectiveModuleId) {
  return moduleId ? state.objectiveScoresByModule[moduleId] || null : null;
}

function simulationScores(moduleId = state.simulationModuleId) {
  if (!moduleId) return {};
  state.simulationScoresByModule[moduleId] ||= {};
  return state.simulationScoresByModule[moduleId];
}

function renderObjectiveQuestion(question, index, answers, score) {
  const key = objectiveAnswerKey(question);
  const result = score?.results?.[key];
  const value = answers[key];
  const reviewedClass = typeof result?.correct === "boolean" ? (result.correct ? "is-correct" : "is-wrong") : "";
  let control = "";
  if (question.type === "fill_blank") {
    const parts = normalizedAnswerParts(question);
    const values = Array.isArray(value) ? value : [value];
    control = `<div class="fill-answer-grid">${parts.map((part, partIndex) => `
      <label class="fill-answer-part"><span>${parts.length > 1 ? `第 ${partIndex + 1} 空` : "你的答案"}</span><input type="text" data-exam-fill="${escapeHtml(key)}" data-part-index="${partIndex}" value="${escapeHtml(values[partIndex] || "")}" placeholder="请输入答案" ${score ? "disabled" : ""}></label>`).join("")}</div>`;
  } else if (["single", "multiple"].includes(question.type)) {
    const selected = new Set(Array.isArray(value) ? value : []);
    control = `<div class="exam-options">${(question.options || []).map((option) => `<label class="exam-option"><input type="${question.type === "multiple" ? "checkbox" : "radio"}" name="${escapeHtml(key)}" value="${escapeHtml(option.key)}" data-exam-choice="${escapeHtml(key)}" ${selected.has(option.key) ? "checked" : ""} ${score ? "disabled" : ""}><b>${escapeHtml(option.key)}</b>${escapeHtml(option.text)}</label>`).join("")}</div>`;
  } else {
    control = `<textarea class="exam-short-answer" data-exam-short="${escapeHtml(key)}" rows="5" placeholder="请写下完整回答" ${score ? "disabled" : ""}>${escapeHtml(value || "")}</textarea>`;
  }

  let review = "";
  if (score) {
    const answerLabel = question.type === "short_answer" ? "原卷参考答案" : question.type === "keyword_answer" ? "参考安全回答" : "正确答案";
    const explanation = question.explanation ? `<p class="answer-explanation"><b>解析</b>${escapeHtml(question.explanation)}</p>` : "";
    const keywordReview = question.type === "keyword_answer" ? `
      <p class="answer-explanation"><b>关键词判定</b>已命中 ${Number(result?.matched_count || 0)} 组，答对需至少 ${Number(result?.minimum_groups || 0)} 组${(result?.required_groups || []).length ? `，且必须包含：${escapeHtml(result.required_groups.join("、"))}` : ""}。</p>
      ${result?.safety_blocked ? `<p class="answer-explanation"><b>安全硬规则</b>${escapeHtml(result.safety_block_reason || "回答包含危险反向指令，本题按 0 分处理。")}</p>` : ""}
      <p class="answer-explanation"><b>已命中</b>${escapeHtml((result?.matched_groups || []).join("、") || "暂无")}</p>
      ${(result?.missing_groups || []).length ? `<p class="answer-explanation"><b>还可补充</b>${escapeHtml(result.missing_groups.join("、"))}</p>` : ""}` : "";
    const manualValue = score.manualScores?.[key];
    const manualScore = question.type === "short_answer" ? `
      <label class="manual-score"><span>本题得分</span><span><input type="number" min="0" max="${Number(question.points || 0)}" step="0.5" data-manual-score="${escapeHtml(key)}" value="${manualValue ?? ""}" ${score.stage === "complete" ? "disabled" : ""}> / ${formatPoints(question.points)} 分</span></label>` : `<span class="auto-score">自动得分：${formatPoints(result?.earned || 0)} / ${formatPoints(question.points)} 分</span>`;
    review = `<div class="answer-review"><span>你的回答：${escapeHtml(result?.actual || "未作答")}</span><em><b>${answerLabel}</b>${escapeHtml(questionReferenceAnswer(question))}</em>${keywordReview}${explanation}${manualScore}</div>`;
  }

  const typeLabel = question.type === "short_answer" ? "问答" : question.type === "keyword_answer" ? "关键词问答" : question.type === "multiple" ? "多选" : question.type === "single" ? "单选" : "填空";
  return `<article class="exam-question ${reviewedClass}" data-question-id="${escapeHtml(key)}"><div class="exam-question-title"><span>${index + 1}. ${escapeHtml(question.prompt)}</span><small>${typeLabel} · ${formatPoints(question.points)} 分</small></div>${control}${review}</article>`;
}

function renderObjectiveExam() {
  const exam = activeExamModule();
  if (!exam) return "";
  const answers = objectiveAnswers();
  const score = objectiveScore();
  const questions = examQuestions(exam);
  const totalPoints = examTotalPoints(exam);
  const manualQuestions = questions.filter((question) => question.type === "short_answer");
  let questionNumber = 0;
  const sections = examSectionGroups(questions).map((group) => {
    const sectionPoints = group.questions.reduce((sum, question) => sum + Number(question.points || 0), 0);
    const content = group.questions.map((question) => renderObjectiveQuestion(question, questionNumber++, answers, score)).join("");
    return `<details open><summary>${escapeHtml(group.title)}（${group.questions.length} 题，共 ${formatPoints(sectionPoints)} 分）</summary><div class="exam-question-list">${content}</div></details>`;
  }).join("");
  const realExam = isRealExam(exam);
  const sourceNote = realExam ? `<div class="real-exam-source-note"><strong>真实考试说明</strong><p>${escapeHtml(exam.score_note || "题目、答案和分值按原卷录入。")} 问答题提交后显示原卷答案，由监考或培训人员录入本题得分。</p>${state.realExamBank?.notice ? `<p>${escapeHtml(state.realExamBank.notice)}</p>` : ""}</div>` : "";
  let reveal = "";
  if (score?.stage === "review") {
    reveal = `<div class="exam-result exam-review-pending" tabindex="-1"><strong>答题已提交，进入批阅</strong><p>请对照每道问答题的原卷答案，在“本题得分”中录入 0 至该题满分；全部录入后即可查看总成绩。</p></div>`;
  } else if (score?.stage === "complete") {
    const percentage = totalPoints ? Math.round((score.score / totalPoints) * 100) : 0;
    const detail = manualQuestions.length
      ? `填空或选择题自动得分 ${formatPoints(score.autoScore)} 分，问答题批阅得分 ${formatPoints(score.manualScore)} 分。`
      : `答对 ${score.correct}/${questions.length} 题。下方已标出你的答案、正确答案和解析。`;
    reveal = `<div class="exam-result" tabindex="-1"><strong>本次得分：${formatPoints(score.score)}/${formatPoints(totalPoints)}（${percentage}%）</strong><p>${detail}</p></div>`;
  }
  const action = !score
    ? `<button class="exam-submit" data-submit-objective>${manualQuestions.length ? "提交答卷并开始批阅" : "交卷并查看成绩"}</button>`
    : score.stage === "review"
      ? `<button class="exam-submit" data-finalize-objective>完成批阅并查看成绩</button>`
      : `<button class="exam-restart" data-reset-objective>再考一次</button>`;
  return `<section class="objective-exam ${realExam ? "real-objective-exam" : ""}"><div class="exam-section-head"><span>共 ${questions.length} 题 · 满分 ${formatPoints(totalPoints)} 分</span><h3>${realExam ? escapeHtml(exam.title) : "开始答题"}</h3><p>${manualQuestions.length ? "请独立完成全部题目；提交前不会显示标准答案。" : "完成所有题目后交卷，即可查看成绩和详细解析。"}</p></div>${sourceNote}${sections}${action}${reveal}</section>`;
}

function scoreObjectiveExam() {
  const exam = activeExamModule();
  if (!exam) return;
  const answers = objectiveAnswers();
  let autoScore = 0;
  let correct = 0;
  const all = examQuestions(exam);
  const unanswered = all.filter((question) => !questionIsAnswered(question, answers[objectiveAnswerKey(question)]));
  if (unanswered.length) {
    showToast(`还有 ${unanswered.length} 题未作答，完成后再交卷。`, true);
    const firstKey = objectiveAnswerKey(unanswered[0]);
    els.testScenario.querySelector(`[data-exam-fill="${firstKey}"], [data-exam-choice="${firstKey}"], [data-exam-short="${firstKey}"]`)?.focus();
    return;
  }
  const results = {};
  all.forEach((question) => {
    const key = objectiveAnswerKey(question);
    const actualAnswer = answers[key];
    if (question.type === "short_answer") {
      results[key] = { correct: null, earned: null, actual: questionAnswerText(question, actualAnswer) };
      return;
    }
    let earned = 0;
    let isCorrect = false;
    if (question.type === "keyword_answer") {
      const keywordScore = keywordAnswerScore(question, actualAnswer);
      earned = keywordScore.earned;
      isCorrect = keywordScore.correct;
      results[key] = {
        ...keywordScore,
        actual: questionAnswerText(question, actualAnswer),
      };
    } else if (question.type === "fill_blank") {
      const parts = normalizedAnswerParts(question);
      const values = Array.isArray(actualAnswer) ? actualAnswer : [actualAnswer];
      let correctParts = 0;
      if (question.order_sensitive === false) {
        const unmatched = [...values];
        parts.forEach((part) => {
          const matchedIndex = unmatched.findIndex((value) => answerMatches(value, part.answer, part.aliases));
          if (matchedIndex >= 0) {
            correctParts += 1;
            unmatched.splice(matchedIndex, 1);
          }
        });
      } else {
        correctParts = parts.filter((part, index) => answerMatches(values[index], part.answer, part.aliases)).length;
      }
      earned = parts.length ? Number(question.points || 0) * (correctParts / parts.length) : 0;
      isCorrect = correctParts === parts.length;
    } else {
      const expected = new Set((question.answers || []).map((item) => String(item)));
      const actual = new Set(Array.isArray(actualAnswer) ? actualAnswer.map((item) => String(item)) : []);
      isCorrect = expected.size === actual.size && [...expected].every((item) => actual.has(item));
      earned = isCorrect ? Number(question.points || 0) : 0;
    }
    earned = Math.round(earned * 100) / 100;
    autoScore += earned;
    if (isCorrect) correct += 1;
    if (question.type !== "keyword_answer") {
      results[key] = { correct: isCorrect, earned, actual: questionAnswerText(question, actualAnswer) };
    }
  });
  const hasManual = all.some((question) => question.type === "short_answer");
  state.objectiveScoresByModule[state.objectiveModuleId] = {
    stage: hasManual ? "review" : "complete",
    score: hasManual ? null : autoScore,
    autoScore,
    manualScore: 0,
    correct,
    results,
    manualScores: {},
  };
  renderScenarioFrame();
  els.testScenario.querySelector(".exam-result")?.focus();
}

function finalizeObjectiveReview() {
  const exam = activeExamModule();
  const score = objectiveScore();
  if (!exam || score?.stage !== "review") return;
  const manualQuestions = examQuestions(exam).filter((question) => question.type === "short_answer");
  const missing = manualQuestions.filter((question) => !Object.prototype.hasOwnProperty.call(score.manualScores || {}, question.id));
  if (missing.length) {
    showToast(`还有 ${missing.length} 道问答题未录入得分。`, true);
    els.testScenario.querySelector(`[data-manual-score="${missing[0].id}"]`)?.focus();
    return;
  }
  const invalid = manualQuestions.find((question) => {
    const value = Number(score.manualScores[question.id]);
    return !Number.isFinite(value) || value < 0 || value > Number(question.points || 0);
  });
  if (invalid) {
    showToast(`“${invalid.prompt}”的得分应在 0 到 ${formatPoints(invalid.points)} 分之间。`, true);
    els.testScenario.querySelector(`[data-manual-score="${invalid.id}"]`)?.focus();
    return;
  }
  score.manualScore = Math.round(manualQuestions.reduce((sum, question) => sum + Number(score.manualScores[question.id]), 0) * 100) / 100;
  score.score = Math.round((score.autoScore + score.manualScore) * 100) / 100;
  score.stage = "complete";
  renderScenarioFrame();
  els.testScenario.querySelector(".exam-result")?.focus();
}

function bindObjectiveExam(root) {
  root.querySelectorAll("[data-exam-fill]").forEach((input) => input.addEventListener("input", () => {
    const key = input.dataset.examFill;
    const values = Array.isArray(objectiveAnswers()[key]) ? [...objectiveAnswers()[key]] : [];
    values[Number(input.dataset.partIndex || 0)] = input.value;
    objectiveAnswers()[key] = values;
  }));
  root.querySelectorAll("[data-exam-short]").forEach((input) => input.addEventListener("input", () => { objectiveAnswers()[input.dataset.examShort] = input.value; }));
  root.querySelectorAll("[data-exam-choice]").forEach((input) => input.addEventListener("change", () => {
    const key = input.dataset.examChoice;
    const checked = [...root.querySelectorAll(`[data-exam-choice="${key}"]:checked`)].map((item) => item.value);
    objectiveAnswers()[key] = checked;
  }));
  root.querySelectorAll("[data-manual-score]").forEach((input) => input.addEventListener("input", () => {
    const score = objectiveScore();
    if (!score || input.value === "") {
      if (score) delete score.manualScores[input.dataset.manualScore];
      return;
    }
    score.manualScores[input.dataset.manualScore] = Number(input.value);
  }));
  root.querySelector("[data-submit-objective]")?.addEventListener("click", scoreObjectiveExam);
  root.querySelector("[data-finalize-objective]")?.addEventListener("click", finalizeObjectiveReview);
  root.querySelector("[data-reset-objective]")?.addEventListener("click", () => {
    delete state.objectiveAnswersByModule[state.objectiveModuleId];
    delete state.objectiveScoresByModule[state.objectiveModuleId];
    renderScenarioFrame();
    els.testScenario.querySelector("input, textarea")?.focus();
  });
}

function renderScenarioFrame() {
  if (state.mode !== "training" && state.mode !== "test") return;
  if (state.route === "exam/objective") {
    els.testScenario.classList.add("objective-only");
    els.testScenario.innerHTML = renderObjectiveExam();
    bindObjectiveExam(els.testScenario);
    return;
  }
  const module = activeModule();
  const scenario = state.scenario;
  const target = state.mode === "test" ? els.testScenario : els.trainingScenario;
  target.classList.remove("objective-only");
  if (!module || !scenario) {
    target.innerHTML = `<div class="scenario-empty">这个模块暂时没有可用场景，请先选择其他模块。</div>`;
    return;
  }
  const isSimulation = state.route === "exam/simulation";
  const scores = isSimulation ? simulationScores() : {};
  const scenarioChoices = moduleScenarios();
  const scenarioNumber = Math.max(1, scenarioChoices.findIndex((item) => item.id === scenario.id) + 1);
  const scenarioAction = isSimulation ? `下一个场景 · ${scenarioNumber}/${scenarioChoices.length}` : "换个场景";
  const focusLabel = isSimulation ? "接待重点" : "练习重点";
  const scenarioStatus = isSimulation ? `<div class="exam-ai-status">考核进度：已完成 ${Object.keys(scores).length}/${moduleScenarios().length} 个场景${scores[scenario.id] != null ? ` · 本场得分：${scores[scenario.id]}/100` : ""}</div>` : "";
  target.innerHTML = `
    <div class="scenario-main">
      <div class="scenario-title-row"><div><span>${isSimulation ? "考核场景" : "陪练场景"}</span><h3>${escapeHtml(scenario.title || scenario.goal || module.title)}</h3></div><button class="change-scenario" data-random-scenario>${scenarioAction} ↗</button></div>
      <div class="scenario-opening"><span>顾客开场</span><p>“${escapeHtml(scenario.opening)}”</p></div>
      ${isSimulation && scenario.task ? `<p class="scenario-task"><b>你的任务：</b>${escapeHtml(scenario.task)}</p>` : ""}${scenarioStatus}
    </div>
    <div class="scenario-focus"><span>${focusLabel}</span><ul>${module.objectives.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`;
  target.querySelector("[data-random-scenario]")?.addEventListener("click", randomScenario);
}

function changePracticeModule(moduleId) {
  if (!exactModuleById(moduleId)) return;
  navigateRoute(state.route, moduleId);
}

function randomScenario() {
  const choices = moduleScenarios();
  if (!choices.length) return;
  const hasUnfinishedWork = state.history.some((item) => item.role === "user") && !state.ended;
  if (hasUnfinishedWork && !window.confirm("切换后将清空当前对话，是否继续？")) return;
  state.scenarioIndex = (state.scenarioIndex + 1) % choices.length;
  selectScenario();
  renderScenarioFrame();
  resetSession();
}

function resetSession() {
  cancelVoiceInput();
  if (state.mode === "learning" || state.route === "exam/objective" || !els.conversationStage) return;
  state.requestSerial += 1;
  state.busy = false;
  state.history = [];
  state.ended = false;
  setRevisionState(false);
  els.input.value = "";
  els.input.disabled = false;
  els.send.disabled = false;
  updateVoiceInputUi();
  els.finish.disabled = true;
  els.finish.textContent = conversationCopy().finish;
  els.turnCount.textContent = "0 轮对话";
  if (state.mode === "qa") {
    els.messages.innerHTML = `<div class="empty-state"><div class="empty-symbol">问</div><h3>输入一个顾客问题</h3><p>接待助手会提供参考回答，并推荐相关课程供你继续学习。</p></div>`;
    return;
  }
  const opening = state.scenario?.opening || "您好，我想先了解一下你们的项目。";
  els.messages.innerHTML = "";
  addMessage("assistant", opening, "AI 顾客");
  state.history.push({ role: "assistant", content: opening });
}

function addMessage(role, text, label, coach = null) {
  els.messages.querySelector(".empty-state")?.remove();
  const row = document.createElement("div");
  row.className = `message-row ${role === "user" ? "user" : ""}`;
  const avatar = role === "user" ? (state.mode === "qa" ? "客" : "我") : (state.mode === "qa" ? "AI" : "客");
  row.innerHTML = `<div class="avatar">${avatar}</div><div class="bubble-wrap"><div class="speaker">${escapeHtml(label)}</div><div class="bubble">${escapeHtml(text)}</div>${coach ? renderCoach(coach) : ""}</div>`;
  els.messages.appendChild(row);
  els.messages.scrollTop = els.messages.scrollHeight;
  return row;
}

function renderCoach(coach) {
  const level = coach.level || "needs_work";
  const label = level === "good" ? "本轮表现不错" : level === "critical" ? "需要立即调整" : "再优化一下";
  const methodology = coach.method_step || coach.knowledge_focus ? `<div class="coach-method"><div><span>接待步骤</span><strong>${escapeHtml(coach.method_step || "按接待流程继续")}</strong></div><div><span>需要用到的知识</span><strong>${escapeHtml(coach.knowledge_focus || "围绕顾客当前问题回答")}</strong></div></div>` : "";
  // A green result already confirms that the employee's wording was good.
  // Showing a replacement script in that state makes the learner think the
  // answer still needs to be copied and, in multi-turn practice, can pull an
  // earlier turn's wording back into the UI.  Keep the suggestion only for
  // needs_work/critical feedback where a concrete repair is useful.
  const suggestion = level === "good"
    ? ""
    : `<div class="coach-suggestion"><span>可以这样说</span>${escapeHtml(coach.suggested_reply || "")}</div>`;
  return `<div class="coach-card ${level}"><div class="coach-title">${label}</div>${methodology}<p><b>可改进之处：</b>${escapeHtml(coach.issue || "")}</p><p><b>为什么：</b>${escapeHtml(coach.why || "")}</p>${suggestion}<div class="coach-next">下一步：${escapeHtml(coach.next_goal || "继续完成需求分析")}</div><div class="coach-actions"><button type="button" class="revise-turn-button" aria-label="修改这次回答">↺ 修改这次回答</button></div></div>`;
}

function setRevisionState(active, turnNumber = 0) {
  state.revising = Boolean(active);
  document.querySelector(".composer-wrap")?.classList.toggle("is-revising", state.revising);
  if (state.revising) {
    els.composerHint.textContent = `正在修改第 ${turnNumber || 1} 轮，重新发送后将更新反馈`;
    els.input.placeholder = "修改你的回复，发送后将更新本轮反馈…";
  } else if (modeCopy[state.mode]) {
    const copy = conversationCopy();
    els.composerHint.textContent = copy.hint;
    els.input.placeholder = copy.placeholder;
  }
}

function updateTrainingEditActions() {
  const buttons = [...els.messages.querySelectorAll(".revise-turn-button")];
  buttons.forEach((button, index) => {
    const available = state.mode === "training" && !state.busy && !state.ended && !state.revising && index === buttons.length - 1;
    button.hidden = !available;
    button.disabled = !available;
  });
}

function reviseLastTrainingTurn() {
  if (state.mode !== "training" || state.busy || state.ended || state.revising) return;
  const assistantTurn = state.history.at(-1);
  const employeeTurn = state.history.at(-2);
  if (assistantTurn?.role !== "assistant" || employeeTurn?.role !== "user") return;
  const rows = [...els.messages.querySelectorAll(".message-row:not(.typing-row)")];
  const assistantRow = rows.at(-1);
  const employeeRow = rows.at(-2);
  if (!assistantRow?.querySelector(".coach-card") || !employeeRow?.classList.contains("user")) return;

  state.history.splice(-2, 2);
  assistantRow.remove();
  employeeRow.remove();
  const turnNumber = state.history.filter((item) => item.role === "user").length + 1;
  setRevisionState(true, turnNumber);
  els.turnCount.textContent = `${turnNumber - 1} 轮对话`;
  els.finish.disabled = true;
  els.input.value = employeeTurn.content;
  els.input.focus();
  els.input.setSelectionRange(els.input.value.length, els.input.value.length);
  updateTrainingEditActions();
  showToast(`已撤回第 ${turnNumber} 轮，修改后发送即可重新评价。`);
}

function addTyping() {
  const row = document.createElement("div");
  row.className = "message-row typing-row";
  const status = state.mode === "qa" ? "接待助手正在查找回答…" : "模拟顾客正在回复…";
  row.innerHTML = `<div class="avatar">${state.mode === "qa" ? "AI" : "客"}</div><div class="bubble-wrap"><div class="speaker">${status}</div><div class="bubble typing"><i></i><i></i><i></i></div></div>`;
  els.messages.appendChild(row);
  els.messages.scrollTop = els.messages.scrollHeight;
  return row;
}

function requestContextKey() {
  return `${state.route}:${state.routeModuleId || ""}:${state.scenario?.id || ""}`;
}

function requestHistory(mode = state.mode, moduleId = activeModuleId()) {
  if (mode === "qa") return [...state.history];
  const module = exactModuleById(moduleId);
  return [{ role: "system", content: `本轮模块：${module?.title || "综合接待"}。目标：${(module?.objectives || []).join("；")}` }, ...state.history];
}

async function sendMessage() {
  const message = els.input.value.trim();
  if (state.voiceCapture) {
    showToast("请先停止录音，确认转写内容后再发送。", true);
    return;
  }
  if (!message || state.busy || state.ended) return;
  const modeSnapshot = state.mode;
  const moduleSnapshot = activeModuleId();
  const scenarioSnapshot = state.scenario?.id;
  const contextSnapshot = requestContextKey();
  const requestId = ++state.requestSerial;
  const isCurrentRequest = () => requestId === state.requestSerial && contextSnapshot === requestContextKey();
  const wasRevising = state.revising;
  const revisedTurnNumber = state.history.filter((item) => item.role === "user").length + 1;
  state.busy = true;
  els.send.disabled = true;
  updateVoiceInputUi();
  els.input.value = "";
  const priorHistory = requestHistory(modeSnapshot, moduleSnapshot);
  const userRow = addMessage("user", message, modeSnapshot === "qa" ? "顾客问题" : "我（员工）");
  state.history.push({ role: "user", content: message });
  if (wasRevising) els.composerHint.textContent = `正在重新评价第 ${revisedTurnNumber} 轮…`;
  updateTrainingEditActions();
  const typing = addTyping();
  try {
    const data = await api("/api/chat", {
      mode: modeSnapshot,
      action: "turn",
      message,
      history: priorHistory,
      scenario_id: scenarioSnapshot,
      api_key: state.apiKey,
      model: state.model,
      prompt_overrides: state.promptOverrides,
    });
    typing.remove();
    if (!isCurrentRequest()) return;
    updateApiStatus(data.meta);
    if (modeSnapshot === "training") {
      const result = data.result;
      addMessage("assistant", result.customer_reply || "顾客暂时没有继续说。", "AI 顾客", result.feedback);
      state.history.push({ role: "assistant", content: result.customer_reply || "" });
      setRevisionState(false);
    } else if (modeSnapshot === "test") {
      const result = data.result;
      addMessage("assistant", result.reply || "顾客暂时没有继续说。", "AI 顾客");
      state.history.push({ role: "assistant", content: result.reply || "" });
    } else {
      renderQAAnswer(data.result, data.retrieved || [], data.citations || []);
      state.history.push({ role: "assistant", content: data.result.answer || "" });
    }
    const turns = state.history.filter((item) => item.role === "user").length;
    els.turnCount.textContent = `${turns} 轮对话`;
    if (modeSnapshot !== "qa") els.finish.disabled = modeSnapshot === "test" ? turns < 4 : turns < 1;
  } catch (error) {
    typing.remove();
    if (!isCurrentRequest()) return;
    userRow.remove();
    if (state.history.at(-1)?.role === "user" && state.history.at(-1)?.content === message) state.history.pop();
    els.input.value = message;
    if (wasRevising) setRevisionState(true, revisedTurnNumber);
    showToast(error.message, true);
  } finally {
    if (!isCurrentRequest()) return;
    state.busy = false;
    if (!state.ended) els.send.disabled = false;
    updateVoiceInputUi();
    updateTrainingEditActions();
    els.input.focus();
  }
}

function renderQAAnswer(result, retrieved, citations) {
  const row = addMessage("assistant", result.answer || "暂时没有找到足够依据。", "AI 接待助手");
  if (result.faq_match) {
    const faqLabel = Number(result.faq_match.candidate_count || 1) > 1 ? "多条常见问答复核后命中" : "命中常见问答标准答案";
    row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-faq-match"><span>${faqLabel}</span><p>匹配问题：${escapeHtml(result.faq_match.question || "相似常见问题")}</p></div>`);
  }
  const route = result.route || {};
  const supportingModules = Array.isArray(route.supporting_modules) ? route.supporting_modules : [];
  const routeModules = [route.primary_module, ...supportingModules].filter(Boolean);
  if (route.intent || routeModules.length) {
    row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-method"><div class="answer-method-head"><span>顾客关注</span><strong>${escapeHtml(route.intent || "一般需求咨询")}</strong></div><div class="answer-method-route"><span>参考模块</span><p>${escapeHtml(routeModules.join(" · ") || "新客接待与需求洞察")}</p></div>${route.method_step ? `<div class="answer-method-step"><span>建议回应步骤</span><p>${escapeHtml(route.method_step)}</p></div>` : ""}</div>`);
  }
  if (result.recommended_action) {
    row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-next-action"><span>接待建议</span><p>${escapeHtml(result.recommended_action)}</p></div>`);
  }
  const uncertainties = Array.isArray(result.uncertainties) ? result.uncertainties.filter(Boolean).slice(0, 4) : [];
  if (uncertainties.length) {
    row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-next-action"><span>需要核实</span><p>${escapeHtml(uncertainties.join("；"))}</p></div>`);
  }
  const references = retrieved.length ? retrieved : citations.map((item) => ({ course_id: item.course_id, title: item.label, module: item.module, chapter: item.chapter }));
  const resolvedReferences = references.map((item) => ({ item, course: resolveReferenceCourse(item) }));
  const unique = resolvedReferences.filter(({ item, course }, index, all) => {
    const key = course?.id || item.title;
    return key && all.findIndex((candidate) => (candidate.course?.id || candidate.item.title) === key) === index;
  }).slice(0, 5);
  const referenceHtml = unique.length ? unique.map(({ item, course }) => {
    const module = course ? moduleById(course.module_id) : null;
    const title = course?.title || item.title;
    const moduleLabel = module?.short_name || module?.title || item.module || "知识模块";
    const chapter = course?.group_title || item.chapter || "";
    if (!course) {
      return `<div class="answer-reference answer-reference-unavailable"><span>${escapeHtml(moduleLabel)}${chapter ? ` · ${escapeHtml(chapter)}` : ""}</span><strong>${escapeHtml(title)}</strong><i>参考资料</i></div>`;
    }
    return `<button class="answer-reference" data-course-id="${escapeHtml(course.id)}" data-course-title="${escapeHtml(course.title)}"><span>${escapeHtml(moduleLabel)}${chapter ? ` · ${escapeHtml(chapter)}` : ""}</span><strong>${escapeHtml(course.title)}</strong><i>查看课程 →</i></button>`;
  }).join("") : `<div class="reference-empty">本次回答参考了通用接待与安全规范。</div>`;
  row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-basis"><div class="answer-basis-title"><span>相关知识与课程</span><small>打开课程查看详情</small></div><div class="answer-reference-list">${referenceHtml}</div></div>`);
  bindCourseButtons(row);
}

async function finishSession() {
  const userTurns = state.history.filter((item) => item.role === "user").length;
  const minimumTurns = state.route === "exam/simulation" ? 4 : 1;
  if (state.mode === "qa" || state.busy || state.ended) return;
  if (state.voiceCapture) {
    showToast("请先停止录音并确认转写内容，再结束本次对话。", true);
    return;
  }
  if (userTurns < minimumTurns) {
    showToast(`再完成 ${minimumTurns - userTurns} 轮对话，即可查看结果。`, true);
    return;
  }
  const modeSnapshot = state.mode;
  const moduleSnapshot = activeModuleId();
  const scenarioSnapshot = state.scenario?.id;
  const contextSnapshot = requestContextKey();
  const requestId = ++state.requestSerial;
  const isCurrentRequest = () => requestId === state.requestSerial && contextSnapshot === requestContextKey();
  state.busy = true;
  updateVoiceInputUi();
  updateTrainingEditActions();
  els.finish.disabled = true;
  els.finish.textContent = "正在生成评分结果…";
  els.input.disabled = true;
  els.send.disabled = true;
  const typing = addTyping();
  try {
    const data = await api("/api/chat", {
      mode: "test",
      action: "finish",
      history: requestHistory(modeSnapshot, moduleSnapshot),
      scenario_id: scenarioSnapshot,
      api_key: state.apiKey,
      model: state.model,
      prompt_overrides: state.promptOverrides,
    });
    typing.remove();
    if (!isCurrentRequest()) return;
    renderAssessment(data.result);
    updateApiStatus(data.meta);
    state.ended = true;
    els.input.disabled = true;
    els.send.disabled = true;
    els.finish.textContent = "评分完成";
  } catch (error) {
    typing.remove();
    if (!isCurrentRequest()) return;
    els.finish.disabled = false;
    els.finish.textContent = conversationCopy().finish;
    els.input.disabled = false;
    els.send.disabled = false;
    showToast(error.message, true);
  } finally {
    if (!isCurrentRequest()) return;
    state.busy = false;
    updateVoiceInputUi();
    updateTrainingEditActions();
  }
}

function renderAssessment(result) {
  if (state.route === "exam/simulation" && state.scenario?.id) {
    simulationScores()[state.scenario.id] = Number(result.total_score || 0);
    renderScenarioFrame();
  }
  const card = document.createElement("div");
  card.className = "assessment-card";
  const dimensions = (result.dimension_scores || []).map((item) => `<div class="score-row"><div class="score-row-head"><span>${escapeHtml(item.name)}</span><strong>${escapeHtml(item.score)}<i>/${escapeHtml(item.max_score)}</i></strong></div><small><b>评分依据</b>${escapeHtml(item.evidence || "对话中未体现")}<br><b>表现说明</b>${escapeHtml(item.comment || "")}</small></div>`).join("");
  const critical = (result.critical_failures || []).map((item) => `<div><b>${escapeHtml(item.code)}</b> ${escapeHtml(item.reason)}${item.evidence ? `<br><small>${escapeHtml(item.evidence)}</small>` : ""}</div>`).join("");
  const scenario = state.scenario || {};
  const standardAnswer = state.route === "exam/simulation" && scenario.reference_answer ? `<div class="report-block standard-answer"><label>参考回答与关键要点</label><p>${escapeHtml(scenario.reference_answer)}</p><ul>${(scenario.must_test || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : "";
  const reportTitle = state.mode === "training" ? "本次陪练报告" : "模拟接待考核结果";
  card.innerHTML = `<div class="assessment-header"><div><span>${reportTitle}</span><p>${escapeHtml(result.summary || "本次对话评分已完成。")}</p></div><strong>${escapeHtml(result.total_score ?? 0)}<i>/100</i></strong></div><div class="score-rows">${dimensions}</div>${critical ? `<div class="critical-block"><b>需要重点改进</b><br>${critical}</div>` : ""}<div class="report-columns"><div class="report-block"><label>做得好的地方</label><p>${escapeHtml((result.strengths || []).join("；") || "继续保持完整沟通。")}</p></div><div class="report-block improve"><label>下次重点练习</label><p>${escapeHtml((result.improvements || []).join("；") || "继续练习需求分析和异议处理。")}</p></div>${standardAnswer}</div>`;
  els.messages.appendChild(card);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function updateApiStatus(meta = {}, health = null) {
  if (typeof health?.api_configured === "boolean") state.backendApiConfigured = health.api_configured;
  if (meta.mock === false) state.apiVerified = true;
  if (!state.apiKey && !state.backendApiConfigured) state.apiVerified = false;
  const connected = state.backendApiConfigured || state.apiVerified;
  els.apiStatus.textContent = meta.degraded
    ? `本轮部分 AI 降级${Array.isArray(meta.fallback_roles) && meta.fallback_roles.length ? `（${meta.fallback_roles.join(" / ")}）` : ""}`
    : connected ? "在线 AI 已就绪" : state.apiKey ? "在线 AI 待连接" : "演示模式";
}

function openModal(id) {
  const backdrop = $(id);
  if (document.activeElement instanceof HTMLElement) modalReturnFocus.set(id, document.activeElement);
  backdrop.classList.remove("hidden");
  backdrop.scrollTop = 0;
  backdrop.querySelector(".modal")?.scrollTo(0, 0);
  document.body.classList.add("modal-open");
  requestAnimationFrame(() => backdrop.querySelector(".modal-close, input, select, button")?.focus());
}

function closeModal(id) {
  if (id === "course-modal") resetCourseModalScroll();
  $(id).classList.add("hidden");
  if (!document.querySelector(".modal-backdrop:not(.hidden)")) document.body.classList.remove("modal-open");
  const trigger = modalReturnFocus.get(id);
  modalReturnFocus.delete(id);
  if (trigger?.isConnected) trigger.focus();
}

function renderModelOptions() {
  const models = [...state.models];
  if (!models.some((item) => item.id === state.model)) models.unshift({ id: state.model, label: `${state.model} · 已保存` });
  const options = models.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join("");
  $("model-name").innerHTML = options;
  $("model-name").value = state.model;
}

function selectModel(model, notify = true) {
  if (!model) return;
  state.model = model;
  localStorage.setItem("kbai_model", state.model);
  renderModelOptions();
  if (notify) showToast(`已切换模型：${state.models.find((item) => item.id === model)?.label || model}`);
}

function openSettings() {
  $("api-key").value = state.apiKey;
  renderModelOptions();
  renderPromptEditors();
  openModal("settings-modal");
}

function renderPromptEditors() {
  const prompts = normalizePromptOverrides(state.promptOverrides);
  $("prompt-qa").value = prompts.qa;
  $("prompt-training-customer").value = prompts.training.customer;
  $("prompt-training-coach").value = prompts.training.coach;
  $("prompt-simulation-customer").value = prompts.simulation.customer;
  $("prompt-simulation-assessment").value = prompts.simulation.assessment;
  $("prompt-save-status").textContent = localStorage.getItem(PROMPT_STORAGE_KEY) ? "已使用本地保存偏好" : "使用系统默认偏好";
}

function savePromptSettings() {
  state.promptOverrides = savePromptOverrides({
    qa: $("prompt-qa").value,
    training: { customer: $("prompt-training-customer").value, coach: $("prompt-training-coach").value },
    simulation: { customer: $("prompt-simulation-customer").value, assessment: $("prompt-simulation-assessment").value },
  });
  renderPromptEditors();
  showToast("三个 AI 的表达偏好已保存，后续对话立即生效。");
}

function resetPromptSettings() {
  state.promptOverrides = savePromptOverrides(PROMPT_PREFERENCE_DEFAULTS);
  renderPromptEditors();
  showToast("已恢复系统默认表达偏好。");
}

async function saveSettings() {
  const candidateKey = $("api-key").value.trim();
  const candidateModel = $("model-name").value.trim() || DEFAULT_MODEL;
  const saveButton = $("save-settings");
  if (!candidateKey) {
    state.apiKey = "";
    state.model = candidateModel;
    state.apiVerified = false;
    localStorage.removeItem("kbai_api_key");
    localStorage.setItem("kbai_model", state.model);
    updateApiStatus({ mock: true });
    closeModal("settings-modal");
    showToast("已进入演示模式。");
    return;
  }
  saveButton.disabled = true;
  saveButton.textContent = "正在连接…";
  els.apiStatus.textContent = "正在连接在线 AI";
  try {
    const validation = await api("/api/chat", {
      mode: "qa",
      action: "turn",
      message: "你好，请确认连接。",
      history: [],
      api_key: candidateKey,
      model: candidateModel,
    });
    if (validation.meta?.mock !== false) throw new Error("API 未返回真实模型结果");
    state.apiKey = candidateKey;
    state.model = candidateModel;
    state.apiVerified = true;
    localStorage.setItem("kbai_api_key", state.apiKey);
    localStorage.setItem("kbai_model", state.model);
    updateApiStatus(validation.meta);
    closeModal("settings-modal");
    showToast("在线 AI 已连接，设置已保存。");
  } catch (error) {
    state.apiVerified = false;
    els.apiStatus.textContent = state.apiKey ? "在线 AI 待连接" : "演示模式";
    showToast(`在线 AI 连接失败，请检查 API Key 或稍后重试。${error.message ? `（${error.message}）` : ""}`, true);
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = "保存并验证";
  }
}

function navigateRoute(route, moduleId = null, options = {}) {
  const { updateHistory = true, replace = false, focus = true } = options;
  const config = ROUTE_CONFIG[route];
  if (!config) return navigateRoute("learning", null, { updateHistory, replace, focus });
  const validModuleId = config.screen === "activity" && moduleId && routeItemById(route, moduleId) ? moduleId : null;
  const nextPath = routePath(route, validModuleId);
  const previousContext = requestContextKey();
  cancelVoiceInput();
  state.requestSerial += 1;
  state.busy = false;
  state.route = route;
  state.routeModuleId = validModuleId;
  state.mode = config.mode;
  if (route === "learning/course") state.learningModuleId = validModuleId;
  if (route === "learning/practice") state.practiceModuleId = validModuleId;
  if (route === "exam/objective") {
    state.objectiveModuleId = validModuleId;
    state.testModuleId = validModuleId;
  }
  if (route === "exam/simulation") {
    state.simulationModuleId = validModuleId;
    state.testModuleId = validModuleId;
  }
  document.querySelectorAll(".typing-row").forEach((row) => row.remove());
  els.input.disabled = false;
  els.send.disabled = false;
  updateVoiceInputUi();
  renderModuleOptions();
  renderRoute();
  if (validModuleId && route === "learning/course") renderLearning();
  if (validModuleId && route === "exam/objective") renderScenarioFrame();
  if (validModuleId && (route === "learning/practice" || route === "exam/simulation")) {
    state.scenarioIndex = 0;
    selectScenario();
    renderScenarioFrame();
    resetSession();
  } else if (route === "qa" && previousContext !== requestContextKey()) {
    resetSession();
  }
  if (updateHistory && window.location.hash !== nextPath) {
    window.history[replace ? "replaceState" : "pushState"](null, "", nextPath);
  } else if (!updateHistory && window.location.hash !== nextPath) {
    window.history.replaceState(null, "", nextPath);
  }
  window.scrollTo({ top: 0, behavior: focus ? "smooth" : "auto" });
  if (focus) {
    els.pageTitle.setAttribute("tabindex", "-1");
    els.pageTitle.focus({ preventScroll: true });
  }
}

function syncRouteFromLocation(focus = true) {
  const parsed = parseRouteHash();
  if (parsed.route === state.route && parsed.moduleId === state.routeModuleId && !parsed.invalid) return;
  navigateRoute(parsed.route, parsed.moduleId, { updateHistory: false, focus });
  if (parsed.invalid) showToast("这个链接无法打开，已返回可选择的页面。", true);
}

async function boot() {
  try {
    const [bootstrap, moduleData, catalogData, health, examBank, pointWaveFaqExam, realExamBank] = await Promise.all([
      api("/api/bootstrap"),
      fetch(staticAsset("learning_modules.json")).then((response) => response.json()),
      fetch(staticAsset("learning_catalog.json")).then((response) => response.json()),
      api("/api/health"),
      fetch(staticAsset("data/comprehensive_exam_bank.json")).then((response) => response.json()),
      fetch(staticAsset("data/point_wave_faq_exam.json")).then((response) => response.json()),
      fetch(staticAsset("data/real_exam_bank.json")).then((response) => response.json()),
    ]);
    state.scenarios = bootstrap.scenarios || [];
    state.modules = moduleData.modules || [];
    state.courses = catalogData.courses || [];
    state.catalogIndex = catalogData.module_index || [];
    state.knowledge = bootstrap.knowledge || {};
    state.examBank = mergePointWaveFaqExam(examBank, pointWaveFaqExam);
    state.realExamBank = realExamBank;
    // The bootstrap payload contains the fixed long prompts. They are used
    // only inside the system envelope; the editable local values remain
    // short presentation preferences.
    state.promptDefaults = bootstrap.prompt_defaults || state.promptDefaults || DEFAULT_PROMPT_OVERRIDES;
    state.promptOverrides = loadPromptOverrides(PROMPT_PREFERENCE_DEFAULTS);
    state.models = bootstrap.models?.length ? bootstrap.models : AVAILABLE_MODELS;
    renderModelOptions();
    els.healthNumber.textContent = state.knowledge.rag_documents || 172;
    renderModuleOptions();
    const requested = parseRouteHash();
    navigateRoute(requested.route, requested.moduleId, { updateHistory: false, focus: false });
    if (requested.invalid) showToast("这个链接无法打开，已返回可选择的页面。", true);
    updateApiStatus({}, health);
    updateVoiceInputUi();
  } catch (error) {
    showToast(`页面数据加载失败，请刷新后重试。${error.message ? `（${error.message}）` : ""}`, true);
  }
}

document.addEventListener("click", (event) => {
  const routeButton = event.target.closest("[data-route]");
  if (!routeButton) return;
  const route = routeButton.dataset.route;
  if (!VALID_ROUTES.has(route)) return;
  navigateRoute(route);
});
els.moduleRouteGrid.addEventListener("click", (event) => {
  const moduleButton = event.target.closest("[data-module-id]");
  if (moduleButton) navigateRoute(state.route, moduleButton.dataset.moduleId);
});
window.addEventListener("popstate", () => syncRouteFromLocation());
window.addEventListener("hashchange", () => syncRouteFromLocation());
els.learningSelect.addEventListener("change", () => {
  state.learningModuleId = els.learningSelect.value;
  renderLearning();
});
els.practiceSelect.addEventListener("change", () => changePracticeModule(els.practiceSelect.value));
els.testSelect.addEventListener("change", () => changePracticeModule(els.testSelect.value));
els.send.addEventListener("click", sendMessage);
els.voiceInput.addEventListener("click", () => { void startVoiceInput(); });
els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});
els.finish.addEventListener("click", finishSession);
els.messages.addEventListener("click", (event) => {
  if (event.target.closest(".revise-turn-button")) reviseLastTrainingTurn();
});
$("clear-chat").addEventListener("click", resetSession);
$("open-settings").addEventListener("click", openSettings);
$("model-name").addEventListener("change", () => selectModel($("model-name").value, false));
$("save-settings").addEventListener("click", saveSettings);
$("save-prompts").addEventListener("click", savePromptSettings);
$("reset-prompts").addEventListener("click", resetPromptSettings);
$("demo-mode").addEventListener("click", () => {
  state.apiKey = "";
  $("api-key").value = "";
  saveSettings();
});
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => closeModal(button.dataset.close)));
document.querySelectorAll(".modal-backdrop").forEach((modal) => modal.addEventListener("click", (event) => {
  if (event.target === modal) closeModal(modal.id);
}));
document.addEventListener("keydown", (event) => {
  const activeModal = document.querySelector(".modal-backdrop:not(.hidden)");
  if (event.key === "Escape") {
    document.querySelectorAll(".modal-backdrop:not(.hidden)").forEach((modal) => closeModal(modal.id));
    return;
  }
  if (event.key !== "Tab" || !activeModal) return;
  const focusable = [...activeModal.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')].filter((item) => item.offsetParent !== null);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});
document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => {
  els.input.value = button.dataset.question;
  els.conversationStage.scrollIntoView({ behavior: "smooth", block: "start" });
  els.input.focus();
}));

boot();
