from app.schemas.tools import ComplianceRequest, ComplianceResult

PROMPT_INJECTION_MARKERS = ("忽略之前", "绕过审批", "直接上线", "ignore previous")
BUILT_IN_COPY_RISK_TERMS = ("最终解释权", "高周转潜力", "热销", "畅销", "爆款")


def check_compliance_rules(request: ComplianceRequest) -> ComplianceResult:
    text = f"{request.title}\n{request.marketing_copy}".lower()
    violations: list[str] = []
    forbidden_terms = {
        term for policy in request.policies for term in policy.forbidden_terms if term.strip()
    }
    for term in sorted(forbidden_terms):
        if term.lower() in text:
            violations.append(f"文案包含禁用词：{term}")
    for term in BUILT_IN_COPY_RISK_TERMS:
        if term.lower() in text:
            violations.append(f"文案包含高风险表述：{term}")
    for marker in PROMPT_INJECTION_MARKERS:
        if marker.lower() in text:
            violations.append(f"检测到高风险执行指令：{marker}")
    for price in request.pricing:
        if not price.eligible:
            violations.append(f"商品 {price.product_id} 未通过价格约束")
        if price.discount_rate > request.max_discount_rate:
            violations.append(f"商品 {price.product_id} 超过最大折扣率")
        if price.margin_rate < request.min_margin_rate:
            violations.append(f"商品 {price.product_id} 低于最低毛利率")
    if not request.policies:
        violations.append("缺少有效政策证据")
    return ComplianceResult(
        passed=not violations,
        violations=violations,
        checked_policy_codes=[policy.code for policy in request.policies],
    )
