document.addEventListener('DOMContentLoaded', function () {
    console.log('Journal Entry Form JS loaded');

    function updateIndices(container) {
        const lines = Array.from(container.querySelectorAll('.journal-line')).filter(l => l.style.display !== 'none');
        lines.forEach((line, i) => {
            line.dataset.index = i;
            line.querySelectorAll('*').forEach(el => {
                ['name', 'id', 'for'].forEach(attr => {
                    if (el.hasAttribute(attr)) {
                        let val = el.getAttribute(attr);
                        // __prefix__ と既存の数字インデックスを置換
                        val = val.replace(/__prefix__/g, i).replace(/-\d+-/g, `-${i}-`).replace(/-\d+$/g, `-${i}`);
                        el.setAttribute(attr, val);
                    }
                });
            });
        });
        const totalInput = container.querySelector('input[name$="-TOTAL_FORMS"]');
        if (totalInput) totalInput.value = lines.length;
    }

    function addJournalLine(container, entryType) {
        const totalInput = container.querySelector('input[name$="-TOTAL_FORMS"]');
        if (!totalInput) {
            console.error('管理フォーム (TOTAL_FORMS) が見つかりません', container);
            return;
        }
        const index = parseInt(totalInput.value, 10);
        const template = container.querySelector('.empty-form-template');
        if (!template) {
            console.error('empty form template が見つかりません', container);
            return;
        }

        const newNode = document.createElement('div');
        newNode.classList.add('journal-line');
        // テンプレート内の __prefix__ を新しいインデックスで置換してセット
        newNode.innerHTML = template.innerHTML.replace(/__prefix__/g, index);
        newNode.style.display = 'block';

        // entry_type フィールドがあれば設定
        const entryTypeInput = newNode.querySelector('[name$="entry_type"]');
        if (entryTypeInput) {
            entryTypeInput.value = entryType;
        }

        // 削除ボタンがなければ追加する
        if (!newNode.querySelector('.remove-line-button')) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'remove-line-button';
            btn.textContent = '行を削除';
            newNode.appendChild(btn);
        }

        // 削除イベントを付与
        newNode.querySelector('.remove-line-button').addEventListener('click', function (e) {
            removeLine(e, container);
        });

        container.appendChild(newNode);
        // インデックス再採番（新しい行を含めて）
        updateIndices(container);
    }

    function removeLine(event, container) {
        const line = event.target.closest('.journal-line');
        if (!line) return;

        const deleteCheckbox = line.querySelector('input[type="checkbox"][name$="-DELETE"]');
        if (deleteCheckbox) {
            // 既存行: DELETE にチェックを入れて非表示
            deleteCheckbox.checked = true;
            line.style.display = 'none';
        } else {
            // 新規追加行: DOMから削除
            line.remove();
            // インデックス再採番
            updateIndices(container);
        }
    }

    // 初期化: 各コンテナの既存行にイベントを付与
    ['debit-lines-container', 'credit-lines-container'].forEach(containerId => {
        const container = document.getElementById(containerId);
        if (!container) return;

        // 既存の行の削除ボタンにイベントを追加
        container.querySelectorAll('.journal-line').forEach(line => {
            const btn = line.querySelector('.remove-line-button');
            if (btn) {
                btn.addEventListener('click', function (e) { removeLine(e, container); });
            }
        });

        // Add ボタン
        const addButton = containerId === 'debit-lines-container' ?
            document.getElementById('add-debit-button') :
            document.getElementById('add-credit-button');

        if (addButton) {
            addButton.addEventListener('click', function () {
                const type = containerId === 'debit-lines-container' ? 'D' : 'C';
                addJournalLine(container, type);
            });
        }

        // 最初にインデックスを揃えておく
        updateIndices(container);
    });
});