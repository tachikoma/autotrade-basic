이 프로젝트는 Python 기반 자동매매 봇이다.

모든 답변은 한국어로 작성하세요.

uv 패키지 관리자를 사용하는 프로젝트이므로, 실행할 때는 `uv run python main.py` 명령어를 사용한다.

목표:
- GitHub Actions에서 자동 실행 가능해야 한다
- 자동매매 입문자를 위한 학습용 프로젝트다

코드 규칙:
- 과도한 추상화나 복잡한 디자인 패턴은 사용하지 않는다
- 초보자도 읽을 수 있는 코드 스타일을 유지한다
- 한 함수는 한 가지 역할만 수행한다
- print/log 메시지는 사람이 이해하기 쉽게 작성한다

작업 설명 규칙:
- 특정 작업(기능 추가, 구조 변경, 설정 변경 등)을 수행한 후에는
  반드시 그 작업이 무엇을 위한 것인지 설명을 덧붙인다
- 설명은 비전공자도 이해할 수 있는 쉬운 한국어로 작성한다
- 기술적인 구현 설명보다는 "이 작업을 왜 했는지"와 "이제 무엇이 가능해졌는지"를 중심으로 설명한다
- 이 설명은 주석, 문서, 또는 출력 메시지 형태로 포함될 수 있다

# Git and Documentation
- **Commit Messages**: Write Git commit messages in **Korean** following the Conventional Commits standard (e.g., `feat: 로그인 기능 구현`).
- **Documentation**: All generated READMEs, API docs, and guides must be in **Korean**.

- **Naming Convention**: Use clear and meaningful **English** for variables, functions, and class names.
- **Principles**: Adhere to Clean Code principles and ensure logical consistency regardless of the model being used.
- 한 줄에 여러 동작을 넣지 않는다