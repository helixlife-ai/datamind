from enum import Enum, auto

class AlchemyEventType(Enum):
    """炼丹流程事件类型"""
    PROCESS_STARTED = auto()
    INTENT_PARSED = auto()
    PLAN_BUILT = auto()
    SEARCH_EXECUTED = auto()
    ARTIFACT_GENERATED = auto()
    OPTIMIZATION_SUGGESTED = auto()
    PROCESS_COMPLETED = auto()
    ERROR_OCCURRED = auto()
    CANCELLATION_REQUESTED = auto()
    PROCESS_CANCELLED = auto()
    PROCESS_CHECKPOINT = auto()  # 处理过程中的检查点事件 