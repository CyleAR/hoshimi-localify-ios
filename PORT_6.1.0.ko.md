# 6.1.0 build 155 / 패치 1.1.0

Android 기준은 `5325a950`의 커스텀 그래픽 설정부터 `8cccfd8`까지다.

- 기존 훅 29개와 런타임 메서드를 메서드 이름·시그니처로 재확인했다. 추가 그래픽 훅 7개와 필드 오프셋도 새 메타데이터에서 얻었다.
- 그래픽 품질 10/20/30/40/100, 렌더 비율 25~200%, 최대 해상도 256~4096, FXAA/SMAA, 그림자 512~4096을 지원한다. Android와 같은 기본 비율 77%, 최대 3384를 사용하며 커스텀 그래픽은 기본 OFF다. 설정 변경은 앱 재실행 때 적용된다.
- Android와 같이 게임 품질 상태를 보존하고, 메인 카메라에 AA·그림자 설정을 적용한다. 후처리가 꺼진 카메라에 AA를 강제로 켜지 않는다. 그림자는 기기 최대 텍스처 크기를 넘지 않는다.
- `prefill_dictionary.json`과 generic의 `{사전이름}`을 지원한다. 완전 일치 → 번역문 필터 → 카드 `+` → 숫자 포맷 → 사전 패턴 → 분할 순서를 유지한다. 긴 사전 단어 우선, 반복 플레이스홀더 일치, 숫자·전각 숫자와 패턴 탐색 예산을 지원한다.
- 알림 문자열 및 앱이 생성하는 `UNMutableNotificationContent`의 제목·부제·본문에 generic 번역을 적용한다. 이미 OS에 전달된 알림이나 앱이 실행되지 않은 상태에서 도착한 원격 푸시를 소급 변경하지 않는다.
- APK Full/Lite 배포, MuMu/LSPosed 호환 수정, Android 로그인 옵션 제거는 Android 전용 변경이다. iOS의 내장 데이터 버전 감지와 다운로드 우선 로딩은 기존 구현을 유지한다.

이번 빌드의 번역 데이터는 Android와 같은 `5ec011e6` (`20261029_005205`)이다. iOS 서브모듈 포인터만 갱신했고 공유 데이터에 새 커밋을 만들지 않았다.

generic 인덱스는 기존 HSGEN2 뒤에 사전 확장부를 붙인다. 기존 바이너리도 읽을 수 있지만, 새 iOS는 다운로드 캐시를 고를 때 확장부 표시를 확인한다. 구형 인덱스가 새 내장 번역을 덮어쓰는 것을 막기 위해서다. 번역 데이터 워크플로가 이 저장소의 `tools/generic_data.py`를 체크아웃하므로, iOS 변경을 푸시한 뒤 번역 데이터 릴리스를 재생성해야 원격 ZIP에도 적용된다. 데이터 저장소의 워크플로 자체를 편집할 필요는 없다.

## 다음 버전 주소 찾기

기존 등록 행 기반 도구가 메서드 수 변경으로 중단되면 아래 메타데이터 경로를 사용한다. 로컬 Il2CppDumper가 필요하며 실행 파일과 분석 출력은 커밋하지 않는다. `dump_ipa.py`는 버전별 폴더에 추출물과 `output/script.json`, `output/dump.cs`를 생성하고 도구 설정은 실행 후 복원한다.

```powershell
chcp 65001 > $null
python tools/dump_ipa.py --ipa dump/ios/game.qualiarts.idolypride-6.0.2-Decrypted.ipa --output build/analysis-6.0.2
python tools/dump_ipa.py --ipa dump/ios/game.qualiarts.idolypride-6.1.0-Decrypted.ipa --output build/analysis-6.1.0
python tools/discover_hook_profile.py --from-ipa dump/ios/game.qualiarts.idolypride-6.0.2-Decrypted.ipa --from-profile profiles/6.0.2.json --to-ipa dump/ios/game.qualiarts.idolypride-6.1.0-Decrypted.ipa --from-script build/analysis-6.0.2/output/script.json --to-script build/analysis-6.1.0/output/script.json --to-dump build/analysis-6.1.0/output/dump.cs --patch-version 1.1.0 --output profiles/6.1.0.json
./build-hook.ps1 -GameVersion 6.1.0
python tools/package_probe.py --ipa dump/ios/game.qualiarts.idolypride-6.1.0-Decrypted.ipa --dylib build/hook-v2/HoshimiLocalify.dylib --hook-plan build/hook-v2/hook-plan.json --font-file PretendardJP-SemiBold.otf --local-data-root hoshimi-local --include-adv --include-master --include-images --include-phone-subtitles --patch-revision 1 --output build/IdolyPride-6.1.0-HoshimiLocalify-v1.1.0.ipa
```

다음 버전에서는 직전 버전의 IPA·프로필·script.json을 `--from-*`에 지정한다.

## 검증

ARM64 테스트와 IPA 정적 검증에 더해 기기에서 다음을 확인한다.

1. 커스텀 그래픽 OFF 상태의 실행·번역·폰트·이미지·ADV·전화 자막·사용자명 치환·라이브 결과 이동.
2. 커스텀 설정 ON 상태에서 품질·해상도·AA·그림자를 바꾼 후 재실행해 홈과 라이브 확인.
3. 사전 치환이 들어간 스킬 설명과 알림. 문제가 있으면 화면과 `hoshimi-ios-hook.log` 보관.
