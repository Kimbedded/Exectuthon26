/* Stable, accessible meaning choices. No fabricated probabilities. */
(function (root) {
  'use strict';
  let lastKey = '';
  function render(pending, selected, choose, disabled = false) {
    const panel = document.getElementById('contextQuestion');
    const options = document.getElementById('contextOptions');
    panel.hidden = !pending;
    if (!pending) { lastKey = ''; options.replaceChildren(); return; }
    const key = JSON.stringify([pending.snapshot_id, pending.options, pending.likelihood]);
    if (key !== lastKey) {
      const firstQuestion = key !== lastKey;
      lastKey = key;
      document.getElementById('contextPrompt').textContent = pending.question || 'Which meaning do you intend?';
      const likelihood = pending.likelihood;
      const measured = likelihood?.method === 'model_vote_share' && likelihood.valid_samples >= 2
        && Array.isArray(likelihood.shares) && likelihood.shares.length === pending.options.length
        && likelihood.shares.every(value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1)
        && Math.abs(likelihood.shares.reduce((sum, value) => sum + value, 0) - 1) < .02;
      document.getElementById('likelihoodNote').textContent = measured
        ? `Model vote share · ${likelihood.valid_samples} valid samples. These estimates compare the listed meanings; they are not accuracy scores. Please choose what the speaker meant.`
        : 'Likelihood not measured. Both meanings are possible; choose what the speaker meant.';
      options.replaceChildren();
      pending.options.forEach((label, index) => {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'idk-choice meaning-choice';
        const number = document.createElement('span'); number.className = 'idk-choice-index'; number.textContent = String(index + 1).padStart(2, '0');
        const content = document.createElement('span'); content.className = 'idk-choice-text';
        const titles = {'Come / be able to attend':'Come or attend','Prepare or cook it':'Prepare or cook the meal','The floor or earth beneath you':'The floor or earth'};
        const hints = {'Come / be able to attend':/dinner/i.test(pending.source || '')?'Be there for dinner':'Be present at the event',
          'Prepare or cook it':'Make the food','Electrical grounding':'Inspect the grounding connection',
          'The floor or earth beneath you':'Look at the surface beneath you'};
        const title = document.createElement('strong'); title.textContent = titles[label] || label;
        const subtitle = document.createElement('small');
        subtitle.textContent = hints[label] || 'Use this meaning';
        content.append(title, subtitle);
        const share = document.createElement('span'); share.className = 'choice-share';
        share.textContent = measured ? Math.round(likelihood.shares[index] * 100) + '%' : '';
        share.hidden = !measured;
        button.append(number, content, share);
        const arrow = document.createElement('span'); arrow.className = 'idk-icon';
        const icon = document.createElement('i'); icon.setAttribute('data-idk-icon', 'chevron-right');
        icon.setAttribute('aria-hidden', 'true'); arrow.append(icon); button.append(arrow);
        if (measured) {
          const track = document.createElement('span'); track.className = 'choice-track'; track.setAttribute('aria-hidden', 'true');
          const fill = document.createElement('span'); fill.style.width = likelihood.shares[index] * 100 + '%'; track.append(fill); button.append(track);
        }
        button.onclick = () => choose(index, pending.snapshot_id);
        options.append(button);
      });
      root.IdkIcons?.render(options);
      if (firstQuestion && document.activeElement === document.body)
        document.getElementById('contextPrompt').focus({preventScroll: true});
    }
    for (const [index, button] of [...options.children].entries()) {
      button.classList.toggle('chosen', selected === index);
      button.setAttribute('aria-pressed', String(selected === index));
      button.disabled = disabled;
    }
  }
  root.ClarificationView = {render};
})(typeof window !== 'undefined' ? window : globalThis);
