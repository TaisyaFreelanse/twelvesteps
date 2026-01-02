"""Service for working with ChromaDB vector store."""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
import os
from pathlib import Path


class VectorStoreService:
    """Service for managing vector embeddings in ChromaDB."""

    def __init__(self, persist_directory: Optional[str] = None):
        """
        if persist_directory is None:
            project_root = Path(__file__).parent.parent.parent
            persist_directory = str(project_root / "chroma_db")

        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )

        self.frames_collection = self.client.get_or_create_collection(
            name="frames",
            metadata={"hnsw:space": "cosine"}
        )

        self.core_collection = self.client.get_or_create_collection(
            name="gpt_self_core",
            metadata={"hnsw:space": "cosine"}
        )

    def add_frame_embedding(
        self,
        frame_id: int,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any]
    ) -> None:
        """
        metadata["frame_id"] = frame_id

        self.frames_collection.add(
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
            ids=[str(frame_id)]
        )

    def update_frame_embedding(
        self,
        frame_id: int,
        content: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update a frame embedding in the vector store."""
        existing = self.frames_collection.get(ids=[str(frame_id)])

        if not existing["ids"]:
            if content and embedding and metadata:
                self.add_frame_embedding(frame_id, content, embedding, metadata)
            return

        new_content = content if content else existing["documents"][0]
        new_embedding = embedding if embedding else None
        new_metadata = metadata if metadata else existing["metadatas"][0]

        if new_embedding:
            self.frames_collection.update(
                ids=[str(frame_id)],
                embeddings=[new_embedding],
                documents=[new_content],
                metadatas=[new_metadata]
            )
        else:
            self.frames_collection.update(
                ids=[str(frame_id)],
                documents=[new_content],
                metadatas=[new_metadata]
            )

    def delete_frame_embedding(self, frame_id: int) -> None:
        """Delete frame embedding from vector store."""
        self.frames_collection.delete(ids=[str(frame_id)])

    def search_frames(
        self,
        query_embedding: List[float],
        user_id: int,
        limit: int = 5
    ) -> Dict[str, Any]:
        """Search for similar frames in the vector store."""
        try:
            results = self.frames_collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where={"user_id": user_id}
            )
            return results
        except Exception as e:
            return {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}

    def search_core(
        self,
        query_embedding: List[float],
        limit: int = 5,
        filter_tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Search for similar chunks in the core collection."""
        try:
            where_filter = None
            if filter_tags:
                where_filter = {"tags": {"$in": filter_tags}}

            results = self.core_collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where_filter
            )
            return results
        except Exception as e:
            return {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}

    def get_core_count(self) -> int:
        """Get number of chunks in GPT-SELF core collection."""
        return self.core_collection.count()

    def get_frames_count(self) -> int:
        """Get number of frames in frames collection."""
        return self.frames_collection.count()

    def add_core_chunk(
        self,
        chunk_id: str,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any]
    ) -> None:
        """Add a chunk to the GPT-SELF core collection."""
        self.core_collection.add(
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
            ids=[chunk_id]
        )

