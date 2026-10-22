from pydantic import BaseModel, ConfigDict


class LeaderboardEntryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    login: str
    elo: int
    balance: int
