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
        Initialize ChromaDB client.
        
        Args:
            persist_directory: Directory to persist ChromaDB data. 
                               Defaults to ./chroma_db in project root.
        """
        if persist_directory is None:
            # Default to project root / chroma_db
            project_root = Path(__file__).parent.parent.parent
            persist_directory = str(project_root / "chroma_db")
        
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Create or get collections
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
        Add frame embedding to vector store.
        
        Args:
            frame_id: Frame ID from database
            content: Frame content text
            embedding: Embedding vector
            metadata: Metadata dict (must include user_id, emotion, blocks, etc.)
        """
        # Ensure frame_id is in metadata
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
        """
        Update existing frame embedding.
        
        Args:
            frame_id: Frame ID
            content: New content (optional)
            embedding: New embedding (optional)
            metadata: New metadata (optional)
        """
        # Get existing data
        existing = self.frames_collection.get(ids=[str(frame_id)])
        
        if not existing["ids"]:
            # Frame doesn't exist, add it
            if content and embedding and metadata:
                self.add_frame_embedding(frame_id, content, embedding, metadata)
            return
        
        # Update with new data or keep existing
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
    
    async def search_frames(
        self, 
        query_embedding: List[float], 
        user_id: int, 
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Search frames by semantic similarity.
        
        Args:
            query_embedding: Query embedding vector
            user_id: Filter by user ID
            limit: Maximum number of results
            
        Returns:
            Dict with 'ids', 'distances', 'metadatas', 'documents'
        """
        results = self.frames_collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where={"user_id": user_id}
        )
        return results
    
    async def search_core(
        self,
        query_embedding: List[float],
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Search GPT-SELF core concepts by semantic similarity.
        
        Args:
            query_embedding: Query embedding vector
            limit: Maximum number of results
            
        Returns:
            Dict with 'ids', 'distances', 'metadatas', 'documents'
        """
        results = self.core_collection.query(
            query_embeddings=[query_embedding],
            n_results=limit
        )
        return results
    
    def add_core_chunk(
        self,
        chunk_id: str,
        content: str,
        embedding: List[float],
        metadata: Dict[str, Any]
    ) -> None:
        """
        Add GPT-SELF core chunk to vector store.
        
        Args:
            chunk_id: Unique chunk identifier
            content: Chunk text content
            embedding: Embedding vector
            metadata: Metadata dict (tags, blocks, frames, etc.)
        """
        self.core_collection.add(
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata],
            ids=[chunk_id]
        )

