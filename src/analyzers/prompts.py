"""
LLM Prompts for SEC Filing Analysis

Centralized prompt templates for different analysis tasks.
Prompts are designed for zero-shot classification with Llama 3.3.
"""


class AnalysisPrompts:
    """Prompt templates for LLM analysis"""

    RED_FLAG_DETECTION = """Analyze this SEC 8-K filing and identify red flags.

FILING CONTENT:
{filing_content}

8-K ITEMS MENTIONED:
{items}

Identify and extract any concerning signals:
1. EXECUTIVE_CHANGE: Executive departures, appointments, or role changes
2. AUDITOR_CHANGE: Change in auditors or accountants (Item 4.01 - very serious)
3. MATERIAL_EVENT: Significant business events, acquisitions, legal matters
4. RISK_LANGUAGE: Phrases about investigations, restatements, material weakness
5. TIMING_FLAG: Unusual filing timing (Friday evening, holiday)
6. FINANCIAL_RESTATEMENT: Non-reliance on financial statements (Item 4.02)

Return ONLY valid JSON (no markdown, no explanation):
{{
  "red_flags": [
    {{
      "type": "EXECUTIVE_CHANGE",
      "title": "Brief title of the finding",
      "details": "One sentence explanation",
      "severity": "high" | "medium" | "low"
    }}
  ],
  "summary": "One sentence summary of key findings"
}}

If no red flags found, return: {{"red_flags": [], "summary": "No significant red flags detected"}}"""

    INSIDER_PATTERN_ANALYSIS = """Analyze these insider transactions for {ticker}:

TRANSACTIONS:
{transactions}

Identify patterns:
1. CLUSTER_SELLING: Multiple insiders selling within 7 days
2. LARGE_SALE: Individual sale > $1M
3. EXECUTIVE_SELLING: C-suite (CEO, CFO, COO) selling significant shares
4. BUYING_SIGNAL: Insiders buying (positive signal)
5. COORDINATED_ACTIVITY: Suspicious timing or coordination

Consider:
- Total value sold vs bought
- Number of insiders involved
- Timing relative to each other
- Ratio of sales to purchases

Return ONLY valid JSON (no markdown):
{{
  "patterns": [
    {{
      "type": "CLUSTER_SELLING",
      "title": "Brief title",
      "severity": "high" | "medium" | "low",
      "details": "One sentence explanation"
    }}
  ],
  "net_activity": "net_selling" | "net_buying" | "neutral",
  "total_sold": 0,
  "total_bought": 0,
  "insiders_selling": 0,
  "insiders_buying": 0,
  "risk_assessment": "One sentence assessment"
}}"""

    RISK_SCORING = """Given these red flags for {ticker}:

RED FLAGS:
{red_flags}

INSIDER PATTERNS:
{insider_patterns}

Calculate a risk score from 0-100:
- 0-30: Low risk, normal business activity
- 31-50: Moderate, worth monitoring
- 51-70: Elevated, multiple concerning signals
- 71-100: High risk, significant warning signs

Scoring guidelines:
- Auditor changes (Item 4.01): +30 points minimum
- Financial restatement (Item 4.02): +40 points minimum
- Executive departure: +10-20 points depending on role
- Insider selling cluster: +15-25 points
- Large insider sale: +10 points
- Multiple signals compound the risk

Return ONLY valid JSON:
{{
  "risk_score": 67,
  "risk_level": "low" | "moderate" | "elevated" | "high",
  "reasoning": "Two sentence explanation of the score"
}}"""

    EXPLANATION_GENERATION = """Explain these risk signals for {ticker} to a retail investor:

Risk Score: {risk_score}/100 ({risk_level})
Red Flags: {red_flags}
Insider Activity: {insider_summary}

Write 2-3 sentences in plain English:
- What was detected
- Why it matters for investors
- What to watch for next

Be direct and actionable. Avoid jargon.
Do NOT give financial advice - just explain the signals objectively.

Return your explanation as plain text (no JSON, no quotes)."""
