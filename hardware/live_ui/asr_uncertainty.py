"""Uncalibrated decoder diagnostics; never a probability of transcript correctness."""
import re,zlib

def quality(text,avg_logprob,min_margin,truncated,clipped_fraction=0.,no_speech_probability=0.):
    reasons=[]
    caption=bool(re.fullmatch(r'\s*[\[(].*(?:blank[_ ]audio|inaudible|music|applause|laughter|silence|birds?|chirping|noise|wind|footsteps|음악|박수|웃음|무음|새소리|잡음).*?[\])]\s*',text,re.I))
    ratio=len(text.encode())/max(1,len(zlib.compress(text.encode())))
    # A decoder stuck in a repetition loop ("yeah yeah yeah...") is not
    # translatable speech: the translation model mirrors the loop (repeating
    # output tokens) until it hits max_tokens without closing its JSON,
    # producing a 502 instead of a result. Block it the same as non_speech
    # instead of forwarding it to the model.
    repetitive=ratio>2.4
    silent=not text.strip() or caption or repetitive or (no_speech_probability>.6 and avg_logprob is not None and avg_logprob< -1.)
    if avg_logprob is not None and avg_logprob< -1.:reasons.append('low_average_logprob')
    if min_margin is not None and min_margin<.7:reasons.append('close_token_candidates')
    if repetitive:reasons.append('repetitive_output')
    if truncated:reasons.append('decoder_limit')
    if clipped_fraction>=.01:reasons.append('audio_clipping')
    if silent:reasons.append('non_speech')
    return {'status':'non_speech' if silent else 'needs_review' if reasons else 'normal',
        'confidence':None,'confidence_calibrated':False,'reasons':reasons,
        'average_token_logprob':avg_logprob,'min_token_margin':min_margin,
        'compression_ratio':ratio,'no_speech_token_probability':no_speech_probability,
        'thresholds':{'average_logprob':-1.,'token_margin':.7,'compression_ratio':2.4,'clipped_fraction':.01},
        'method':'decoder heuristics, not calibrated transcript accuracy'}
