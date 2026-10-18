/* Automatic dictionary options from the completed result; no search form. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const labels = {exact: 'Dictionary word', base_form: 'Word form', prefix: 'Starts with', similar: 'Possible spelling', contains: 'Contains'};
  let lastKey = '', generation = 0, currentPayload = null, currentTerms = [], selectedTerm = 0;
  let selectedWordIndex = -1;

  function message(text, failed = false) {
    byId('dictionaryStatus').textContent = text;
    byId('dictionaryStatus').className = failed ? 'error' : '';
  }

  async function request(path, options = {}) {
    const response = await fetch('/api/dictionary/' + path, options);
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Could not load word options.');
    return result;
  }

  function clearResults() {
    byId('dictionaryTerms').replaceChildren();
    byId('dictionaryMatches').replaceChildren();
    byId('dictionaryRelated').replaceChildren();
    byId('dictionaryRelatedLabel').hidden = true;
    byId('dictionaryMatchesLabel').hidden = true;
    byId('dictionaryMatches').hidden = true;
    byId('dictionaryMeanings').replaceChildren();
    byId('dictionaryHeading').textContent = 'Choose a word above.';
    byId('dictionaryMore').hidden = true;
    byId('dictionaryRetry').hidden = true;
    currentTerms = [];
  }

  function markWord(button) {
    for (const id of ['dictionaryMatches', 'dictionaryRelated'])
      for (const item of byId(id).children) item.setAttribute('aria-pressed', String(item === button));
  }

  function showRelatedWords(match) {
    const related = byId('dictionaryRelated');
    related.replaceChildren();
    const seen = new Set([match.term.toLowerCase()]);
    for (const item of match.meanings) {
      for (const word of item.synonyms || []) {
        const normalized = word.trim().toLowerCase();
        if (!normalized || seen.has(normalized) || seen.size > 10) continue;
        seen.add(normalized);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'dictionary-match';
        button.textContent = word;
        button.title = 'Related word · ' + item.domain;
        button.setAttribute('aria-pressed', 'false');
        button.onclick = async () => {
          const tick = ++generation;
          markWord(button);
          byId('dictionaryHeading').textContent = 'Loading meanings for ' + word + '…';
          byId('dictionaryMeanings').replaceChildren();
          byId('dictionaryMore').hidden = true;
          try {
            const data = await request('search?' + new URLSearchParams({q: word, limit: '1', language: 'en'}));
            if (tick !== generation) return;
            const found = data.matches?.[0];
            if (!found || !['exact', 'base_form'].includes(found.match_type)) {
              byId('dictionaryHeading').textContent = 'No dictionary meanings found for ' + word + '.';
              return;
            }
            renderMeanings({...found, total_meanings: found.meanings.length});
          } catch (error) {
            if (tick !== generation) return;
            byId('dictionaryHeading').textContent = 'Could not load meanings. Select the word to retry.';
            message(error.message, true);
          }
        };
        related.append(button);
      }
    }
    byId('dictionaryRelatedLabel').hidden = !related.children.length;
  }

  function renderMeanings(match) {
    const meanings = byId('dictionaryMeanings');
    meanings.replaceChildren();
    meanings.scrollTop = 0;
    const total = match.total_meanings || match.meanings.length;
    byId('dictionaryHeading').textContent = match.term + ' · ' + match.meanings.length
      + (total > match.meanings.length ? ' of ' + total : '') + ' possible meaning(s)';
    for (const [index, item] of match.meanings.entries()) {
      const card = document.createElement('article');
      card.className = 'dictionary-meaning';
      const title = document.createElement('h3');
      title.textContent = (index + 1) + ' · ' + item.domain;
      const definition = document.createElement('p');
      definition.className = 'dictionary-definition';
      definition.textContent = item.meaning;
      card.append(title, definition);
      if (item.synonyms?.length) {
        const synonyms = document.createElement('p');
        synonyms.className = 'dictionary-synonyms';
        synonyms.textContent = 'Related words for this meaning: ' + item.synonyms.join(', ');
        card.append(synonyms);
      }
      if (item.example) {
        const example = document.createElement('p');
        example.className = 'dictionary-example';
        example.textContent = 'Example: ' + item.example;
        card.append(example);
      }
      if (item.context_words?.length) {
        const context = document.createElement('p');
        context.className = 'dictionary-credit';
        context.textContent = 'Also mentioned: ' + item.context_words.join(', ');
        card.append(context);
      }
      const credit = document.createElement('p');
      credit.className = 'dictionary-credit';
      credit.textContent = item.source + (item.part_of_speech ? ' · ' + item.part_of_speech : '');
      card.append(credit);
      meanings.append(card);
    }
    const more = byId('dictionaryMore');
    more.hidden = total <= match.meanings.length;
    more.disabled = false;
    more.textContent = 'View all meanings for ' + match.term;
    const tick = generation;
    more.onclick = async () => {
      more.disabled = true;
      try {
        const data = await request('search?' + new URLSearchParams({q: match.term, limit: '1', language: 'en'}));
        if (tick !== generation || !data.matches?.length) return;
        const seen = new Set(match.meanings.map(item => item.entry_key));
        const all = [...match.meanings, ...data.matches[0].meanings.filter(item => !seen.has(item.entry_key))];
        match.meanings = all;
        renderMeanings(match);
      } catch (error) {
        if (tick === generation) message(error.message, true);
      } finally {
        if (tick === generation) more.disabled = false;
      }
    };
  }

  function showTerm(index) {
    generation += 1; // Discard an older 'View all' request when selection changes.
    selectedTerm = index;
    for (const [i, button] of [...byId('dictionaryTerms').children].entries())
      button.setAttribute('aria-pressed', String(i === index));
    const term = currentTerms[index];
    byId('dictionaryMatches').replaceChildren();
    const showAlternatives = term.matches.length > 1
      || term.matches[0].match_type !== 'exact';
    byId('dictionaryMatches').hidden = !showAlternatives;
    byId('dictionaryMatchesLabel').hidden = !showAlternatives;
    for (const [i, match] of term.matches.entries()) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'dictionary-match';
      button.setAttribute('aria-pressed', String(i === 0));
      const word = document.createElement('span');
      word.textContent = match.term;
      const type = document.createElement('small');
      type.textContent = labels[match.match_type] || 'Word option';
      button.append(word, type);
      button.onclick = () => {
        generation += 1;
        markWord(button);
        const selected = (window.currentWordState?.words || []).findIndex(item =>
          item.word.toLowerCase() === match.term.toLowerCase());
        if (selected >= 0) window.selectDictionaryWord?.(selected);
        showRelatedWords(match);
        renderMeanings(match);
      };
      byId('dictionaryMatches').append(button);
    }
    showRelatedWords(term.matches[0]);
    renderMeanings(term.matches[0]);
  }

  async function loadSuggestions(payload, key) {
    const tick = ++generation;
    clearResults();
    message('Finding word options from this result…');
    try {
      const data = await request('suggestions', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
      if (tick !== generation || key !== lastKey) return;
      if (data.basis === 'none') {
        message('English word options are available when one side of the conversation is English.');
        return;
      }
      if (!data.terms?.length) {
        message('No useful dictionary options found for this result.');
        return;
      }
      currentTerms = data.terms;
      for (const [index, term] of currentTerms.entries()) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'dictionary-match';
        button.textContent = term.observed;
        button.onclick = () => {
          const selected = (window.currentWordState?.words || []).findIndex(item =>
            item.word.toLowerCase() === term.observed.toLowerCase());
          if (selected >= 0) window.selectDictionaryWord?.(selected);
          showTerm(index);
        };
        byId('dictionaryTerms').append(button);
      }
      showTerm(0);
      window.updateDictionarySelection?.(window.currentWordState?.word_index ?? -1,
        window.currentWordState?.words || []);
      message('Words found in the English ' + (data.basis === 'source' ? 'source' : 'translation')
        + '. Compare meanings and related words; suggestions do not replace the translation.');
    } catch (error) {
      if (tick !== generation || key !== lastKey) return;
      clearResults();
      message(error.message, true);
      byId('dictionaryRetry').hidden = false;
    }
  }

  window.updateDictionarySuggestions = state => {
    const event = state?.event;
    const result = event?.translation;
    const pending = ['loading', 'thinking', 'transcribing', 'error'].includes(state?.stage);
    const nonSpeech = event?.asr_quality?.status === 'non_speech'
      || /^\s*\[(?:BLANK_AUDIO|NO_SPEECH|SILENCE)\]\s*$/i.test(event?.transcript || '')
      || /^\s*\[(?:BLANK_AUDIO|NO_SPEECH|SILENCE)\]\s*$/i.test(result?.source || '');
    if (pending || nonSpeech || !result?.source || !result?.translation) {
      const key = pending ? 'pending' : 'empty';
      if (key !== lastKey) {
        lastKey = key;
        generation += 1;
        currentPayload = null;
        clearResults();
        byId('dictionaryResult').textContent = '';
        message(pending ? 'Waiting for the next completed translation…' : 'Word options will appear automatically after a translation.');
      }
      return;
    }
    const payload = {
      source: result.source, translation: result.translation,
      source_language: result.source_language || state.source_language || 'en',
      target_language: result.target_language || state.target_language || 'ko',
      context: (event.transcript || '').slice(-6000)
    };

    window.updateDictionarySelection = (index, words) => {
      selectedWordIndex = index;
      for (const button of document.querySelectorAll('#dictionaryTerms button, #dictionaryMatches button')) {
        const term = button.querySelector('span')?.textContent || button.textContent.split('\n')[0];
        const match = (words || []).findIndex(item => item.word.toLowerCase() === term.toLowerCase());
        button.classList.toggle('chosen', match === index);
        button.setAttribute('aria-pressed', String(match === index));
      }
    };
    const key = JSON.stringify(payload);
    if (key === lastKey) return;
    lastKey = key;
    currentPayload = payload;
    byId('dictionaryResult').textContent = (state.preview_mode ? 'Sample result · ' : '') + payload.source + '\n→ ' + payload.translation;
    loadSuggestions(payload, key);
  };

  byId('dictionaryRetry').onclick = () => {
    if (currentPayload) loadSuggestions(currentPayload, lastKey);
  };
  request('stats').then(stats => {
    byId('dictionaryCounts').textContent = Number(stats.terms).toLocaleString() + ' words/phrases · '
      + Number(stats.meanings).toLocaleString() + ' meanings · English definitions';
  }).catch(() => { byId('dictionaryCounts').textContent = 'Dictionary connection unavailable.'; });
})();
