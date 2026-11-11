from pydantic import BaseModel


class AchnasotSyncResponse(BaseModel):
    status: str
    last_id: int | None = None
    fetched: int = 0
    sent: int = 0
