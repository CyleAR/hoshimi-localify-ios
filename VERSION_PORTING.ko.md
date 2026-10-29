# iOS 게임 버전 업데이트 작업

6.1.0부터 메서드 구성이 달라진 경우에는 [메타데이터 이름·시그니처 재탐색 절차](PORT_6.1.0.ko.md)를 따른다. 최신 기본 빌드 대상은 6.1.0이다.

훅 주소는 `profiles/<게임 버전>.json`에 보관한다. 이 파일에는 원본 IPA와 UnityFramework의 SHA-256, 게임 빌드 번호, 29개 훅 위치, 폰트·전화 자막 등에 쓰는 런타임 메서드 8개의 주소와 IL2CPP 모듈별 메서드 행 또는 전역 메서드 포인터 인덱스가 들어 있다. 게임 업데이트 때 기존 RVA를 그대로 쓰거나 일정한 오프셋만 더하지 않는다.

## 새 버전의 주소 재탐색

복호화한 새 IPA를 `dump/ios/game.qualiarts.idolypride-<새 버전>-Decrypted.ipa`에 둔다. 이전 버전 IPA도 `dump/ios`에 보관해야 한다. 다음 예시의 버전과 패치 버전을 실제 값으로 바꿔 실행한다.

```powershell
chcp 65001 > $null
python tools/discover_hook_profile.py --from-ipa dump/ios/game.qualiarts.idolypride-6.0.2-Decrypted.ipa --from-profile profiles/6.0.2.json --to-ipa dump/ios/game.qualiarts.idolypride-6.0.3-Decrypted.ipa --patch-version 1.0.1 --output profiles/6.0.3.json
```

이 도구는 IL2CPP 코드 등록 테이블에서 이전 버전과 같은 모듈·메서드 행을 찾고, 메서드 수와 시작 명령을 대조한다. `username_adv`, `username_message`, `username_notification`, `live_scene`, `live_result`는 전역 메서드 포인터 테이블의 같은 인덱스를 따라 찾는다. 이 5개에 주소 이동량 추정은 사용하지 않는다. 메서드 구성이나 명령이 바뀌어 판단할 수 없으면 실패하므로, 실패한 지점을 수동 분석한 뒤 도구와 프로필을 갱신해야 한다. 정적 확인과 별개로 기기에서 각 기능을 확인한다.

새 프로필의 게임 버전·빌드·SHA-256·주소를 확인하고 빌드한다. `build-hook.ps1`은 프로필과 IPA가 맞는지, 훅 시작 명령·IL2CPP 등록 행·분기·코드 여유 공간이 유효한지 검사한다. 환경에 따라 `HOSHIMI_LLVM_BIN`에 NDK의 LLVM `bin` 폴더를 지정한다.

```powershell
chcp 65001 > $null
./build-hook.ps1 -GameVersion 6.0.3
python tools/package_probe.py --ipa dump/ios/game.qualiarts.idolypride-6.0.3-Decrypted.ipa --dylib build/hook-v2/HoshimiLocalify.dylib --hook-plan build/hook-v2/hook-plan.json --font-file PretendardJP-SemiBold.otf --local-data-root hoshimi-local --include-adv --include-master --include-images --include-phone-subtitles --patch-revision 1 --output build/IdolyPride-6.0.3-HoshimiLocalify-v1.0.1.ipa
```

출력 파일이 이미 있으면 다른 이름을 쓰거나, 기존 결과물이 재생성 가능한 빌드 파일인지 확인한 후 제거한다. 서브모듈 `hoshimi-local`의 데이터는 수정하지 않는다. 빌드 출력과 원본 IPA는 Git에 올리지 않는다.

```powershell
chcp 65001 > $null
$env:PYTHONPATH='build/test-runtime'
python -m unittest discover -s tools -p 'test_*.py'
```

테스트가 통과해도 실제 실행 성공을 뜻하지 않는다. SideStore/iLoader에서 기존 `game.qualiarts.idolypride.kr` 앱으로 업데이트한 후 번역·폰트·ADV·MasterDB·generic·이미지·사용자명·전화 자막·FPS/라이브 결과 기능을 화면과 `hoshimi-ios-hook.log`로 확인한다. 앱을 삭제하면 다운로드 데이터를 잃을 수 있다. 새 게임 버전에서는 우선 기기 검증을 마친 뒤 배포한다.
