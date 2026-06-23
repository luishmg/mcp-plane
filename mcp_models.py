from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

class MCPContent(BaseModel):
    type: str = "text"
    text: str

class MCPToolResult(BaseModel):
    content: List[MCPContent]
    isError: bool = False

class PlaneTask(BaseModel):
    title: str
    description: Optional[str] = Field(None, max_length=1000)
    status: Optional[str] = Field("TODO", pattern="^[A-Z]+$")
    priority: Optional[str] = Field("MEDIUM", enum=["LOW", "MEDIUM", "HIGH"])
    due_date: Optional[datetime] = None

class MCPInitializeRequest(BaseModel):
    protocolVersion: str
    authentication: Optional[dict] = None

class PlaneTaskResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    status: str
    priority: str
    created_at: datetime