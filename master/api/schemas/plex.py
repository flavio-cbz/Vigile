"""Pydantic v2 schemas for Plex Media Server integration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PlexSession(BaseModel):
    """Represents an active Plex streaming session."""

    model_config = ConfigDict(extra="ignore")

    session_key: Optional[str] = Field(default=None, description="Plex session unique key")
    user: str = Field(default="Unknown", description="Username or account title")
    user_thumb: Optional[str] = Field(default=None, description="User avatar URL/path")
    title: str = Field(..., description="Media item title or episode title")
    grandparent_title: Optional[str] = Field(default=None, description="Show/Series title for episodes")
    parent_title: Optional[str] = Field(default=None, description="Season title")
    media_type: str = Field(default="unknown", description="Type: movie, episode, track")
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0, description="Playback progress percentage")
    state: str = Field(default="playing", description="State: playing, paused, buffering")
    player_device: str = Field(default="Unknown Device", description="Device or client name")
    player_platform: Optional[str] = Field(default=None, description="Client platform e.g. iOS, Android, Web")
    quality_profile: str = Field(default="Direct Play", description="Quality: Direct Play, Transcode, Direct Stream")
    bandwidth_kbps: int = Field(default=0, ge=0, description="Streaming bandwidth in kbps")
    started_at: int = Field(default=0, description="Session start timestamp")
    transcode: bool = Field(default=False, description="Whether transcoder is active")
    video_decision: Optional[str] = Field(default=None, description="Transcode decision: copy, transcode")
    audio_decision: Optional[str] = Field(default=None, description="Audio transcode decision")
    speed: Optional[float] = Field(default=None, description="Transcode speed multiplier")
    thumb: Optional[str] = Field(default=None, description="Poster artwork path")


class PlexLibrary(BaseModel):
    """Summary information for a Plex library section."""

    model_config = ConfigDict(extra="ignore")

    key: str = Field(..., description="Library section key/id")
    title: str = Field(..., description="Library title")
    type: str = Field(..., description="Library type: movie, show, artist")
    count: int = Field(default=0, ge=0, description="Total media items count")
    total_size_bytes: int = Field(default=0, ge=0, description="Total estimated size on disk")
    last_scanned_at: Optional[int] = Field(default=None, description="Timestamp of last scanner execution")


class PlexMedia(BaseModel):
    """Metadata representation for a media item in Plex."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="RatingKey or unique Plex media ID")
    title: str = Field(..., description="Title of movie or episode")
    year: Optional[int] = Field(default=None, description="Release year")
    rating: Optional[float] = Field(default=None, description="Rating")
    duration_ms: int = Field(default=0, ge=0, description="Media duration in milliseconds")
    file_size_bytes: int = Field(default=0, ge=0, description="File size on disk in bytes")
    added_at: int = Field(default=0, description="Timestamp when media was added")
    thumb_path: Optional[str] = Field(default=None, description="Artwork relative path in Plex API")


class PlexWatchHistoryEntry(BaseModel):
    """Historique de visionnage d'une session terminée ou scrobblée."""

    model_config = ConfigDict(extra="ignore")

    id: Optional[int] = Field(default=None, description="Database primary key")
    node_id: str = Field(..., description="Vigile node ID hosting Plex")
    user: str = Field(..., description="Username")
    title: str = Field(..., description="Media title")
    grandparent_title: Optional[str] = Field(default=None)
    media_type: str = Field(default="movie")
    viewed_at: int = Field(..., description="Timestamp of session completion")
    duration_watched_s: int = Field(default=0)
    progress_percent: float = Field(default=100.0)
    device: str = Field(default="Unknown")
    quality: str = Field(default="Direct Play")


class PlexServerInfo(BaseModel):
    """Plex Media Server health and platform info."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(default="Plex Media Server")
    version: str = Field(default="Unknown")
    platform: str = Field(default="Linux")
    transcoder_active: bool = Field(default=False)
    online: bool = Field(default=True)
    port: int = Field(default=32400)


class PlexStats(BaseModel):
    """Aggregated Plex statistics."""

    model_config = ConfigDict(extra="ignore")

    sessions_active: int = Field(default=0)
    sessions_today: int = Field(default=0)
    most_watched_user: str = Field(default="N/A")
    top_media: List[str] = Field(default_factory=list)
    library_summary: Dict[str, Any] = Field(default_factory=dict)
    cache_size_bytes: int = Field(default=0)
