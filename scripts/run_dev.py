import os
import sys
import uvicorn

# Setup environment
os.environ["ENV"] = "dev"
os.environ["ALLOW_INSECURE"] = "true"
os.environ["DEBUG"] = "true"
os.environ["SERVER_SECRET_KEY"] = "6afb6c924c406278c2cb8ed3160d8ecdc79f7aede87a6a1d58866b2810e27c3e"
os.environ["JWT_SECRET_KEY"] = "a4be50992d4bb3a4e641f0a32627f26377b361915f4e3f94f146737b29c7ca0a"

sys.path.insert(0, os.path.abspath("."))

if __name__ == "__main__":
    uvicorn.run("master.main:app", host="127.0.0.1", port=8000, reload=False)
