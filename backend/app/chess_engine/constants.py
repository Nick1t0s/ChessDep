import chess

PIECE_VALUES: dict[int, int] = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9,
}
DEP_TARGETS: dict[int, tuple[int, ...]] = {
    chess.PAWN: (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN),
    chess.KNIGHT: (chess.ROOK, chess.QUEEN),
    chess.BISHOP: (chess.ROOK, chess.QUEEN),
    chess.ROOK: (chess.QUEEN,),
}
DEP_LIMIT_PER_GAME = 10
LETTER_TO_TYPE: dict[str, int] = {"P": chess.PAWN, "N": chess.KNIGHT, "B": chess.BISHOP,
                                  "R": chess.ROOK, "Q": chess.QUEEN, "K": chess.KING}
TYPE_TO_LETTER: dict[int, str] = {v: k for k, v in LETTER_TO_TYPE.items()}
COLOR_NAME: dict[bool, str] = {chess.WHITE: "white", chess.BLACK: "black"}
