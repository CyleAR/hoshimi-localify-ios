# iOS 게임 버전 업데이트 작업

게임 업데이트 절차는 이 문서 하나에 유지하고, 버전별 주소는 `profiles/<게임 버전>.json`에 추가한다. 버전마다 별도의 PORT 문서를 만들지 않는다.

현재 기본 대상은 게임 **6.1.1 build 156 / 패치 1.1.1**이다. 6.1.0과 비교해 메서드 이름·시그니처로 기존 대상 29개, 그래픽 훅 7개, 런타임 함수 12개를 재확인했다. 그래픽 필드 위치는 같으며 68개 테스트와 빌드·IPA 검증이 통과했다. 실기 확인은 별도로 필요하다.

## 입력과 프로필

복호화한 IPA를 `dump/ios/game.qualiarts.idolypride-<버전>-Decrypted.ipa`에 둔다. 직전 버전 IPA와 프로필도 보관한다. 원본 IPA와 빌드·분석 출력은 Git에 올리지 않는다.

프로필에는 IPA/UnityFramework SHA-256, 게임 빌드 번호, 메서드 이름·시그니처, RVA, 등록 포인터와 그래픽 필드 오프셋을 저장한다. 함수마다 주소 이동량이 다를 수 있으므로 기존 RVA에 일정한 오프셋을 더하지 않는다.

## 메타데이터와 훅 주소 재탐색

로컬 Il2CppDumper가 필요하다. 기본 위치는 `build/il2cppdumper/tool/Il2CppDumper.exe`이며 다른 위치라면 `dump_ipa.py --dumper <실행파일>`로 지정한다. 도구는 버전별 폴더에 추출물과 `output/script.json`, `output/dump.cs`를 생성하고 실행 후 Dumper 설정을 복원한다.

아래 세 버전을 다음 업데이트에 맞게 바꾼다. 직전 버전 분석 출력이 있으면 첫 번째 dump 명령은 생략할 수 있다.

```powershell
chcp 65001 > $null
$previousGameVersion = '6.1.0'
$gameVersion = '6.1.1'
$patchVersion = '1.1.1'
python tools/dump_ipa.py --ipa "dump/ios/game.qualiarts.idolypride-$previousGameVersion-Decrypted.ipa" --output "build/analysis-$previousGameVersion"
python tools/dump_ipa.py --ipa "dump/ios/game.qualiarts.idolypride-$gameVersion-Decrypted.ipa" --output "build/analysis-$gameVersion"
python tools/discover_hook_profile.py --from-ipa "dump/ios/game.qualiarts.idolypride-$previousGameVersion-Decrypted.ipa" --from-profile "profiles/$previousGameVersion.json" --to-ipa "dump/ios/game.qualiarts.idolypride-$gameVersion-Decrypted.ipa" --from-script "build/analysis-$previousGameVersion/output/script.json" --to-script "build/analysis-$gameVersion/output/script.json" --to-dump "build/analysis-$gameVersion/output/dump.cs" --patch-version $patchVersion --output "profiles/$gameVersion.json"
```

메서드 이름·정규화한 시그니처로 새 주소를 찾고, 등록 테이블과 시작 명령을 대조한다. 그래픽용 추가 함수와 필드도 새 메타데이터에서 얻는다. 대상이 여러 개이거나 시작 명령이 바뀌면 도구가 중단하므로 수동 분석 후 도구·프로필을 갱신한다. 검증 조건을 생략해 통과시키지 않는다.

`--from-script`와 `--to-script`를 생략하는 구형 등록 행 기반 경로도 남아 있다. 메서드 구성이 달라지면 실패할 수 있으므로 현재 작업은 위 메타데이터 경로를 사용한다.

## 빌드와 패키징

새 프로필의 버전·빌드·지문·주소를 확인한다. `build-hook.ps1`은 프로필과 IPA, 시작 명령·등록 포인터·래퍼 분기·게이트웨이 여유 공간을 검증한다. 필요하면 `HOSHIMI_LLVM_BIN`에 NDK LLVM의 `bin` 폴더를 지정한다. 위의 `$gameVersion`과 `$patchVersion`을 유지한 PowerShell 세션에서 실행한다.

```powershell
chcp 65001 > $null
./build-hook.ps1 -GameVersion $gameVersion
python tools/package_probe.py --ipa "dump/ios/game.qualiarts.idolypride-$gameVersion-Decrypted.ipa" --dylib build/hook-v2/HoshimiLocalify.dylib --hook-plan build/hook-v2/hook-plan.json --font-file PretendardJP-SemiBold.otf --local-data-root hoshimi-local --include-adv --include-master --include-images --include-phone-subtitles --patch-revision 1 --output "build/IdolyPride-$gameVersion-HoshimiLocalify-v$patchVersion.ipa"
```

출력이 이미 있으면 다른 파일명을 쓰거나 재생성 가능한 빌드 결과인지 확인한 뒤 제거한다. `--patch-revision 1`은 원본 게임 빌드 번호 뒤에 `.1`을 붙인다. 현재 설치 빌드 번호는 `156.1`이다. 같은 게임 버전의 후속 설치가 필요하면 이 값을 증가시킨다.

공유 번역 데이터는 `hoshimi-local`을 읽는다. 이식 작업에서 번역 원본을 편집하지 않는다. 기본 게임 버전과 README·AGENTS의 현재 대상도 새 프로필에 맞게 갱신한다.

## 테스트와 기기 확인

```powershell
chcp 65001 > $null
$env:PYTHONPATH='build/test-runtime;tools'
python -m unittest discover -s tools -p 'test_*.py'
```

테스트가 통과해도 실제 실행 성공을 뜻하지 않는다. SideStore/iLoader에서 기존 **아이프라**, 번들 ID `game.qualiarts.idolypride.kr` 앱으로 업데이트 설치한다. 앱을 삭제하면 다운로드 데이터를 잃을 수 있다.

1. 커스텀 그래픽 OFF 상태에서 홈 진입·번역·폰트·MasterDB·generic·이미지·ADV·사용자명·전화 자막·FPS·라이브 결과 이동을 확인한다.
2. 커스텀 그래픽 ON 상태에서 품질·해상도·AA·그림자를 바꾸고 재실행한 뒤 홈과 라이브를 확인한다.
3. 사전 치환이 들어간 스킬 설명과 알림을 확인한다. 문제가 있으면 앱을 다시 실행하기 전에 화면과 `hoshimi-ios-hook.log`를 보관한다.

기기 검증을 마친 뒤 배포한다.

## 그래픽·generic 이식 참고

6.1.0에서 Android `5325a950`의 커스텀 그래픽 설정부터 `8cccfd8`까지를 참고해 이식했다.

- 그래픽 품질 10/20/30/40/100, 렌더 비율 25~200%, 최대 해상도 256~4096, FXAA/SMAA, 그림자 512~4096을 지원한다. 기본 비율은 77%, 최대 3384이며 커스텀 그래픽은 기본 OFF다. 설정 변경은 재실행 때 적용된다.
- 게임 품질 상태를 보존하고 메인 카메라에 AA·그림자 설정을 적용한다. 후처리가 꺼진 카메라에 AA를 강제로 켜지 않으며 그림자는 기기 최대 텍스처 크기를 넘지 않는다.
- `prefill_dictionary.json`과 generic의 `{사전이름}`을 지원한다. 완전 일치 → 번역문 필터 → 카드 `+` → 숫자 포맷 → 사전 패턴 → 분할 순서다. 긴 사전 단어 우선, 반복 플레이스홀더 일치, 숫자·전각 숫자와 탐색 예산을 지원한다.
- 게임 알림 문자열과 앱이 생성하는 `UNMutableNotificationContent`의 제목·부제·본문에 generic 번역을 적용한다. 이미 OS에 전달된 알림이나 앱이 실행되지 않은 상태에서 도착한 원격 푸시는 소급 변경하지 않는다.
- APK Full/Lite 배포, MuMu/LSPosed 호환 수정, Android 로그인 옵션 제거는 Android 전용 변경이다. iOS는 내장 데이터 버전 감지와 다운로드 우선 로딩을 사용한다.

## 원격 번역 데이터 호환성

generic 인덱스는 HSGEN2 뒤에 사전 확장부를 붙인다. 새 iOS는 다운로드 캐시를 고를 때 확장부 표시를 확인해 구형 인덱스가 새 내장 번역을 덮어쓰는 것을 막는다.

번역 데이터 워크플로는 이 저장소의 `tools/generic_data.py`를 체크아웃한다. 컴파일러 형식을 변경했으면 iOS 변경을 푸시한 뒤 번역 데이터 릴리스를 재생성해야 원격 ZIP에도 반영된다. 이 때문에 데이터 저장소 워크플로를 별도로 편집할 필요는 없다.
