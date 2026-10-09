# Morning FM

Monocle의 최신 Weekend Opener 칼럼을 한국어로 요약하고 MP3/RSS로 발행합니다.
기존 `https://novvave.github.io/morning-fm/feed.xml` 및 과거 에피소드 URL/GUID를 유지합니다.

## 운영자가 설정할 항목

1. PR 검토·병합 후 Settings → Secrets and variables → Actions에서 repository secrets
   `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`를 등록합니다. 키는 코드/로그/변수에 넣지 않습니다.
2. Settings → Pages → Source를 **GitHub Actions**로 설정합니다. 기본 `GITHUB_TOKEN`으로
   push한 커밋은 기존 branch 기반 Pages 배포를 시작하지 않으므로 워크플로가 직접 배포합니다.
3. Actions 실행과 기본 브랜치에 대한 bot push를 허용합니다. 브랜치 보호가 push를 막으면
   유료 호출 전에 checkpoint push 단계가 실패합니다. 별도 PAT는 필요하지 않습니다.
4. repository variable `MORNING_FM_ENABLED=true`를 설정하면 운영을 활성화합니다.
   미설정/false이면 수동 실행도 건너뜁니다. 초기 상태는 비용 발생 없이 비활성입니다.
5. Actions → Morning FM publish → Run workflow(main)로 첫 실행을 확인합니다.
   `feed.xml`, 새 MP3 URL, Pages deployment 결과를 확인합니다.
6. GitHub 개인 Notifications 설정에서 Actions 실패 알림을 활성화합니다.
   실패는 job의 nonzero exit와 run summary에 표시됩니다. 메일/Slack 자동 전송은 구성하지 않았습니다.
   public 저장소는 60일간 활동이 없으면 schedule이 비활성화될 수 있으므로 장기 미발행 시 확인합니다.

매일 08:17 KST/JST(UTC 23:17)에 **최신 글 한 개만** 확인합니다. 과거 누락분을 일괄 생성하지 않습니다.
스케줄은 GitHub 부하에 따라 지연될 수 있습니다. 같은 원문 URL은 수정되어도 재발행하지 않습니다.
하루 최대 새 에피소드 1개, 입력 본문 최대 20,000자(기존 추출 최대 15단락),
요약 출력 최대 512 tokens / 저장 요약 최대 4,000자입니다. 웹 자동화에는 Gmail 권한이 필요 없습니다.
기존 마지막 에피소드는 Gmail Monocle Minute이며, 이 자동화의 대상인 Weekend Opener와 다릅니다.

## 실패와 재실행

`publication_state.json`은 canonical 원문 URL의 SHA-256을 키로 사용합니다.
기존 TXT+MP3의 원문 URL도 중복 검사하며, 날짜+URL 해시 파일명은 같은 날짜의 덮어쓰기를 방지합니다.
`reserved → summary_pending → summary_ready → tts_pending → audio_ready → published` 순서로
각 상태를 commit/push합니다. 요약·음성 요청 전 pending이 원격에 저장되어야 호출합니다.
`summary_ready`는 요약을 재사용하고 `audio_ready`는 RSS만 다시 생성합니다.
새 글이 있어도 미완료 에피소드부터 복구합니다. pending 상태는 단순 재실행으로 재호출하지 않습니다.
Anthropic SDK 자동 retry를 껐고 ElevenLabs POST도 자동 retry하지 않습니다.

**외부 유료 API와 Git 저장소 사이에 원자적 트랜잭션은 없습니다.** API 응답을 받기 전 timeout,
runner 종료, 결과 checkpoint push 실패가 나면 과금됐는지 자동 판별할 수 없습니다.
이 경우 비용 보존을 위해 발행을 중단합니다. 운영자는 provider usage/요청 기록과 원격 상태를 확인한 뒤:

- `summary_pending`: 결과를 복구할 수 있으면 `summary`와 `status=summary_ready`를 기록합니다.
  미처리가 확인된 경우에만 `reserved`로 되돌립니다.
- `tts_pending`: 올바른 MP3를 해당 `filename`으로 복구 후 `audio_ready`로 기록합니다.
  미처리가 확인된 경우에만 `summary_ready`로 되돌립니다.

수정은 PR로 기록하고 병합 후 다시 실행합니다. 결과를 확인하지 않고 상태를 되돌리면 재과금될 수 있습니다.
자동화와 동시에 로컬 유료 실행을 하지 마세요. workflow concurrency는 Actions 실행끼리만 직렬화합니다.
Pages 실패는 이미 저장된 에피소드를 다시 생성하지 않습니다. 다음 실행은 중복 skip 후 Pages를 다시 배포합니다.
RSS는 완성된 MP3 checkpoint 이후 생성하며, 새 글이 없으면 RSS lastBuildDate를 갱신하지 않습니다.
배포에는 RSS/MP3/선택적 cover.jpg만 포함하며 처리 상태와 원문 발췌 TXT는 포함하지 않습니다.
현재 저장소에 cover.jpg가 없으므로 필요하면 운영자가 추가하세요.

## 로컬 검증과 호환성

Python 3.12 권장:

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -v
python publish_briefing.py --dry-run
# 실제 유료 발행: 두 키 설정, 깨끗한 main checkout, git author/push 설정 필요
python publish_briefing.py --push
```

`python monocle_briefing.py`도 안전한 runner로 연결됩니다. 기존 `--source gmail`은 유지하지만
Gmail 사용 시 기존 Google OAuth 패키지/credentials.json/token.json을 별도 설치·설정해야 합니다.
로컬에서는 **명시적으로 --push를 지정해야** commit/push합니다. --push 없는 발행은 로컬 checkpoint만
남기므로 휘발성 runner에서 사용하면 안 됩니다. `--dry-run`은 키 없이 원문·중복을 확인하고 파일/유료 API를 변경하지 않습니다.
테스트는 네트워크와 유료 API를 mock 처리합니다. 실제 Monocle DOM/접근 제한, provider 권한·잔액,
bot push 권한, Pages 배포는 운영 설정 후 수동 실행으로 검증해야 합니다.
