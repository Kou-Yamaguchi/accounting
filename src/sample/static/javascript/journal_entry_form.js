document.addEventListener('DOMContentLoaded', function() {
    const formsetContainer = document.querySelector('#formset-container');
    const totalForms = document.querySelector('#id_{{ formset.prefix }}-TOTAL_FORMS');
    const emptyFormTemplate = document.querySelector('#empty-form');

    /**
     * 新しい行を追加する関数
     * @param {string} type - 'D' (借方) または 'C' (貸方)
     * @param {HTMLElement} container - 追加先のコンテナ要素
     */
    function addJournalLine(type, container) {
        // フォームの総数を取得し、新しいインデックスとする
        let currentTotal = parseInt(totalForms.value);
        let newIndex = currentTotal;

        // テンプレートから新しいフォーム行を複製
        let newForm = emptyFormTemplate.cloneNode(true);
        newForm.id = ''; // IDを削除して表示可能にする
        newForm.style.display = 'block';
        newForm.classList.add('journal-line');

        // フォーム内の name/id 属性を新しいインデックスに置き換え
        let formHtml = newForm.innerHTML.replace(/__prefix__/g, newIndex);
        newForm.innerHTML = formHtml;
        
        // entry_type の hidden field に 'D' または 'C' を設定
        const entryTypeInput = newForm.querySelector(`[name$="entry_type"]`);
        if (entryTypeInput) {
             entryTypeInput.value = type;
        }

        // 削除ボタンに関数をアタッチ
        newForm.querySelector('.remove-line-button').addEventListener('click', removeLine);

        // コンテナに追加
        container.appendChild(newForm);

        // TOTAL_FORMS の値をインクリメント
        totalForms.value = currentTotal + 1;
    }

    /**
     * 行を削除する関数
     */
    function removeLine(event) {
        const line = event.target.closest('.journal-line');
        // line が既存の行（PKを持つ）で DELETE チェックボックスがある場合
        const deleteCheckbox = line.querySelector('[name$="-DELETE"]');
        
        if (deleteCheckbox) {
            // 既存の行の場合は、削除チェックボックスにチェックを入れる
            deleteCheckbox.checked = true;
            // 見た目上は隠すが、フォームセットには送信する
            line.style.display = 'none';
        } else {
            // 新しく追加した行（PKを持たない）の場合は、DOMから削除
            line.remove();
            // TOTAL_FORMS のデクリメントと、残りの行のインデックス再採番は複雑なので、
            // 簡略化のために新しく追加した行の削除は TOTAL_FORMS をそのままにし、
            // サーバーサイドで余分な空行が保存されないように処理するのが一般的。
            // 厳密にやるには、削除後に残りのフォームのインデックスを再採番する必要がある。
        }
    }

    // 初期化: 既存の行を借方/貸方に振り分ける
    document.querySelectorAll('.journal-line').forEach(line => {
        const entryTypeInput = line.querySelector(`[name$="entry_type"]`);
        if (entryTypeInput) {
            if (entryTypeInput.value === 'D') {
                document.querySelector('#debit-lines-container').appendChild(line);
            } else if (entryTypeInput.value === 'C') {
                document.querySelector('#credit-lines-container').appendChild(line);
            }
        }
        line.querySelector('.remove-line-button').addEventListener('click', removeLine);
    });

    // 「科目を追加」ボタンにイベントリスナーを設定
    document.querySelector('#add-debit-button').addEventListener('click', function() {
        addJournalLine('D', document.querySelector('#debit-lines-container'));
    });

    document.querySelector('#add-credit-button').addEventListener('click', function() {
        addJournalLine('C', document.querySelector('#credit-lines-container'));
    });
});