def extract_repo_name(git_url: str) -> str:
    """Git URL에서 리포지토리명 추출"""
    if not git_url:
        return "repo"
    name = git_url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name
