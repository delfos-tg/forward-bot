from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot_meg.config import config

db = create_engine(config['DATABASE_URI'])
Session = sessionmaker(db)
