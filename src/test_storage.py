from domain import CMMEntity
from storage import StoragePort


class InMemoryStorage(StoragePort):
    """An in-memory storage adapter for testing."""
    
    def __init__(self):
        self.data = {}
    
    def save_file(self, file_path: str, cmm_entity: CMMEntity) -> None:
        """Saves a file's CMM entities to memory."""
        self.data[file_path] = cmm_entity
    
    def get_file(self, file_path: str):
        """Retrieves a file's CMM entities from memory."""
        return self.data.get(file_path)
    
    def upsert_file(self, file_path: str, cmm_entity: CMMEntity) -> None:
        """Updates or inserts a file's CMM entities."""
        self.data[file_path] = cmm_entity
