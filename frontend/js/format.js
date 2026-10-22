export const END_REASON_RU = {
  checkmate: 'Мат',
  stalemate: 'Пат',
  insufficient_material: 'Недостаточно материала',
  fifty_move: 'Правило 50 ходов',
  threefold: 'Троекратное повторение',
  resign: 'Сдача',
  timeout: 'Время вышло',
  timeout_vs_insufficient: 'Время вышло, но у соперника недостаточно материала',
  agreement: 'Ничья по соглашению',
  abort: 'Партия отменена',
  abort_no_first_move: 'Партия отменена: не сделан первый ход',
};

export const PIECE_NAME_RU = { P: 'Пешка', N: 'Конь', B: 'Слон', R: 'Ладья', Q: 'Ферзь', K: 'Король' };

export const DEP_REASON_RU = {
  WOULD_CHECK_OPPONENT: 'Даст шах сопернику',
  NOT_YOUR_TURN: 'Сейчас не ваш ход',
  DEP_ALREADY_USED_THIS_TURN: 'Деп в этом ходу уже сделан',
  DEP_LIMIT_REACHED: 'Лимит депов исчерпан',
  GAME_NOT_ACTIVE: 'Партия завершена',
};

export function fmtCrystals(n) {
  return Number(n).toLocaleString('ru-RU') + ' ◈';
}

export function fmtClock(ms) {
  if (ms < 10000) return (Math.max(0, ms) / 1000).toFixed(1);
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m + ':' + String(s).padStart(2, '0');
}
