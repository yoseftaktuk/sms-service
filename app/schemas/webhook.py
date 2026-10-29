from pydantic import BaseModel, Field


class NedarimWebhookResponse(BaseModel):
    WEBDocID: int = Field(description="Internal numeric id for Nedarim CallBackId cross-ref")
