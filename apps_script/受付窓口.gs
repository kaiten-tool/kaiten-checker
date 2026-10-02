/**
 * 回転率チェッカー → Googleスプレッドシートの受付窓口（Apps Script）
 *
 * スプレッドシート「回転率チェッカー記録」の 拡張機能 → Apps Script に貼り付けて、
 * ウェブアプリとして公開する。合言葉は コードに書かず、
 * プロジェクトの設定 → スクリプト プロパティ に「TOKEN」という名前で登録する。
 *
 * アプリから届いた実戦を「結果」シートに1行、「履歴」シートに記録ごとの行で追加する。
 * 同じIDの実戦がすでに「結果」シートにあれば、二重に書き込まない。
 */

const RESULT_SHEET = '結果';
const HISTORY_SHEET = '履歴';

function doPost(e) {
  let body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return reply({ ok: false, error: 'bad request' });
  }

  const token = PropertiesService.getScriptProperties().getProperty('TOKEN');
  if (!token || body.token !== token) {
    return reply({ ok: false, error: 'unauthorized' });
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const book = SpreadsheetApp.getActiveSpreadsheet();
    const resultSheet = book.getSheetByName(RESULT_SHEET);
    const historySheet = book.getSheetByName(HISTORY_SHEET);
    if (!resultSheet || !historySheet) {
      return reply({ ok: false, error: 'sheet not found' });
    }

    const existing = new Set(existingIds(resultSheet));
    const saved = [];
    (body.sessions || []).forEach(function (session) {
      const id = String(session.id || '');
      if (!id) return;
      if (!existing.has(id)) {
        appendRows(resultSheet, [session.result || []]);
        appendRows(historySheet, session.history || []);
        existing.add(id);
      }
      // すでにあった場合も「受け取り済み」として返し、アプリ側で送信済みにする。
      saved.push(id);
    });
    return reply({ ok: true, saved: saved });
  } finally {
    lock.releaseLock();
  }
}

function existingIds(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  return sheet.getRange(2, 1, lastRow - 1, 1).getValues().map(function (row) {
    return String(row[0]).replace(/^'/, '');
  });
}

function appendRows(sheet, rows) {
  if (!rows.length) return;
  const width = Math.max.apply(null, rows.map(function (row) { return row.length; }));
  const values = rows.map(function (row) {
    const filled = row.slice();
    while (filled.length < width) filled.push('');
    // 文字は先頭に ' を付けて、「1/41.0」が日付に、時刻が日付型に変わらないようにする。
    return filled.map(function (value) {
      return typeof value === 'string' && value !== '' ? "'" + value : value;
    });
  });
  sheet.getRange(sheet.getLastRow() + 1, 1, values.length, width).setValues(values);
}

function reply(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
