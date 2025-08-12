def score_sentiment(headline: str, benzinga_item: dict | None = None):
    """Return (label, score, source). Prefers Benzinga; falls back to FinBERT, then VADER."""
    # 1) Benzinga sentiment if present
    if benzinga_item:
        bz_sent = benzinga_item.get("sentiment")
        if bz_sent:
            # Normalize
            label = str(bz_sent).lower()
            if label in ("bullish","positive","very bullish"): 
                return "bullish", 0.8, "benzinga"
            if label in ("bearish","negative","very bearish"): 
                return "bearish", -0.8, "benzinga"
            if label in ("neutral",): 
                return "neutral", 0.0, "benzinga"

    # 2) FinBERT via transformers
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
        import torch
        model_name = "yiyanghkust/finbert-tone"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        clf = pipeline("text-classification", model=model, tokenizer=tokenizer, return_all_scores=True)
        out = clf(headline)[0]  # list of dicts with label & score
        scores = {d['label'].lower(): d['score'] for d in out}
        pos = scores.get("positive", 0.0)
        neg = scores.get("negative", 0.0)
        neu = scores.get("neutral", 0.0)
        score = round(pos - neg, 4)
        if score > 0.1: return "bullish", score, "finbert"
        if score < -0.1: return "bearish", score, "finbert"
        return "neutral", score, "finbert"
    except Exception:
        pass

    # 3) VADER fallback
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        vs = analyzer.polarity_scores(headline)
        score = round(vs['compound'], 4)
        if score > 0.1: return "bullish", score, "vader"
        if score < -0.1: return "bearish", score, "vader"
        return "neutral", score, "vader"
    except Exception:
        # Last resort
        return "neutral", 0.0, "unknown"
