from sqlalchemy import Column, String, Integer, DateTime
from .base import Base

class Subscription(Base):
    __tablename__ = 'subscriptions'
    
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64))
    plan_type = Column(String(32))
    expire_at = Column(DateTime)
    remaining_minutes = Column(Integer)
