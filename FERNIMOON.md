## Source-first documentary workflow (v4)

For videos like Tacoma Narrows (1940), the previous pipeline created a script first, then accepted loosely matching Pixabay tags (foreign bridges, models, galaxy or highways). **This is disabled in production.** Before Gemini or ElevenLabs is contacted, `fernimoon.research.research_topic` searches Wikimedia Commons for the *named event itself*, requiring event/name/date matches, reuse-rights metadata and a downloadable film or photograph. Real film is preferred; one archived 2-minute film may appear in several Short scenes with different source offsets. Historic `.ogv`/`application/ogg` video, including 640×480 material, is supported.

When no event-specific real footage/photo is available, research may use only a matching **public-domain/CC0 illustration**, which is visibly labeled `ILLUSTRATION`. If neither exists, the job ends with `SOURCE QUALITY GATE` **before paid AI narration**. No random “cinematic” stock B-roll may be substituted. Thus some subjects (especially modern online legends with no authentic available photography) will fail safely until suitable licensed art is available.

Gemini receives the research list and must cite an existing `source_id` in every scene; `research.json` and `sources.json` record provenance for review. Original landscape documentary images are letterboxed in 9:16 to avoid cropping out the event itself. **Limitations:** Commons uploader descriptions and license metadata are not independent historical authentication. A source name may match an event but not depict every spoken claim; editorial review remains necessary before publication. This workflow does not use an image-captioning visual model or original news/archive licensing connector. For new external archive sources, confirm their rights separately.

# FERNIMOON STUDIO — tạo YouTube Shorts từ điện thoại

Bổ sung độc lập cho repository **`bacuabesua1997-coder/fernimoon-shorts.`** (có dấu chấm cuối). Toàn bộ mã TypeScript, HyperFrames, tài liệu và cấu hình gốc được giữ nguyên. Các lệnh `npm run pipeline`, `npm test` cũ vẫn hoạt động như trước. Hệ thống mới chạy bằng **Python 3.12 + FFmpeg**, không cần cài thêm thư viện Python hoặc Node.

## Video được tạo như thế nào?

1. **Gemini API** viết kịch bản tiếng Anh gồm 5–7 cảnh, mở đầu thu hút, nội dung và câu kết; khoảng 84–104 từ cho video 40 giây. Chủ đề có thể nhập bằng tiếng Việt hoặc tiếng Anh.
2. **Pixabay Videos API** tìm các clip `video_type=film`, tải MP4 thật về máy dựng. Mỗi cảnh có 2–3 truy vấn thay thế; ưu tiên video dọc, không lặp ID video trong cùng một Short. Không có API tạo ảnh/video AI, không dùng endpoint tìm ảnh, không dùng ảnh tĩnh làm cảnh.
3. **ElevenLabs** tạo toàn bộ lời đọc tiếng Anh trong một yêu cầu `/with-timestamps`. Phụ đề và các điểm chuyển cảnh lấy từ timestamp ký tự do ElevenLabs trả về, không chia đều thời gian theo số từ.
4. **FFmpeg** crop giữa khung hình, dựng dọc **1080 × 1920, 30 fps**, gắn thương hiệu **FERNIMOON STUDIO**, đốt phụ đề động với từ đang đọc được tô vàng và phóng nhẹ. Âm thanh được cân âm lượng, xuất H.264/yuv420p + AAC, MP4 `faststart`.
5. Kiểm tra lại kích thước, codec và thời lượng cả âm thanh lẫn hình ảnh bằng **ffprobe**, sau đó mới đưa video vào Artifacts.

## Cải thiện Hook & Retention (v2)

Workflow có thêm mục **story_style**: `mystery` (bí ẩn, mặc định), `history` (lịch sử), `science` (khoa học). Nhập chủ đề như trước; mọi chế độ vẫn viết và đọc tiếng Anh, vẫn chỉ sử dụng footage thật trên Pixabay và cùng bốn Secrets đã có. Không cần tạo JSON thủ công hoặc API mới.

Gemini được hướng dẫn cân nhắc ba mở đầu trước khi chọn một câu hook **5–12 từ**, đưa thông tin cụ thể vào giây đầu; các cảnh sau hé lộ thông tin theo diễn biến và câu kết **5–18 từ** cung cấp lời giải có căn cứ hoặc nêu rõ điều chưa chắc chắn. Hook quá dài hoặc kết quá dài sẽ yêu cầu Gemini sửa lại một lần. Trong video, từ được đọc trong **3 giây đầu** có phụ đề lớn hơn. Đây là điều chỉnh cách kể và đồ họa, không phải cam kết tăng lượt xem. Chế độ `history` không gọi stock footage là tư liệu lưu trữ gốc.

Tính năng này **không** tạo MV, nhạc hát Suno hay hoạt hình 2D/3D; các nội dung đó cần renderer/generator riêng. Nguồn audio vẫn từ ElevenLabs; dựng video vẫn FFmpeg và footage Pixabay.

Chọn 35, 40 hoặc 45 giây trên Actions. Để giữ giọng tự nhiên, chỉ chỉnh tempo tối đa ±20%, đồng thời điều chỉnh tất cả timestamp phụ đề/cảnh theo cùng tỷ lệ. Nếu giọng đọc quá ngắn/dài, quy trình báo lỗi, không cắt mất lời đọc. CLI cho phép mọi số giây nguyên từ 35 đến 45.

## Thiết lập một lần trên GitHub

Workflow phải nằm trên nhánh mặc định `main` để GitHub hiển thị nút **Run workflow**. Nếu thay đổi được cung cấp qua pull request, merge pull request trước.

### 1. Thêm Secrets

Mở repository trên **Chrome/Safari**, đăng nhập tài khoản chủ repo:

**Settings → Secrets and variables → Actions → New repository secret**

Liên kết trực tiếp: <https://github.com/bacuabesua1997-coder/fernimoon-shorts./settings/secrets/actions>

Tạo bốn Secrets với tên chính xác:

| Secret | Giá trị cần điền | Nơi lấy |
| --- | --- | --- |
| `GEMINI_API_KEY` | Gemini API key | [Google AI Studio](https://aistudio.google.com/apikey) |
| `PIXABAY_API_KEY` | Pixabay API key | [Pixabay API docs](https://pixabay.com/api/docs/) sau khi đăng nhập |
| `ELEVENLABS_API_KEY` | Key có quyền Text to Speech | [ElevenLabs](https://elevenlabs.io/app/settings/api-keys) |
| `ELEVENLABS_VOICE_ID` | ID giọng tiếng Anh bạn được phép dùng | Chọn một giọng trong thư viện ElevenLabs, sao chép **Voice ID**, không phải tên giọng |

Không điền key vào source code, ô chủ đề, file JSON hoặc bình luận/issue. Workflow chỉ truyền Secrets vào bước kiểm tra cấu hình và bước tạo video; không ghi key vào log hoặc Artifacts. Bạn phải tự nhập giá trị key vào GitHub Secrets; mã nguồn không cung cấp key hay quota.

Tùy chọn trong tab **Variables** (không bắt buộc):

| Variable | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Tên model Gemini hỗ trợ structured JSON output mà tài khoản có quyền dùng |
| `ELEVENLABS_MODEL` | `eleven_multilingual_v2` | Model ElevenLabs tương thích giọng đã chọn, `language_code=en` và timestamps |

Nếu fork chưa bật Actions, vào **Actions** và bật workflows. Các key cần có quota tương ứng; phí/quota nhà cung cấp và phút GitHub Actions phụ thuộc tài khoản.

### 2. Nhập chủ đề từ điện thoại

1. Mở [Actions của repository](https://github.com/bacuabesua1997-coder/fernimoon-shorts./actions).
2. Chọn **FERNIMOON STUDIO - Create Short**.
3. Nhấn **Run workflow**, chọn nhánh `main`.
4. Điền **topic**, ví dụ `Why sea turtles return to the beach where they were born` hoặc `Tại sao cây trong rừng quan trọng với sự sống`.
5. Chọn **duration**: `35`, `40` hoặc `45`, rồi nhấn **Run workflow**.
6. Mở lần chạy vừa tạo. Khi trạng thái xanh, cuộn xuống **Artifacts**, nhấn **FERNIMOON-STUDIO-…**, tải ZIP và giải nén.

Nếu ứng dụng GitHub không hiển thị đầy đủ **Run workflow** hoặc **Artifacts**, mở liên kết bằng trình duyệt; bật **Trang web cho máy tính / Desktop site** nếu cần. Không cần máy tính riêng, server, Colab hoặc thao tác Codex để chạy video.

Gói Artifact giữ **14 ngày**, chứa:

| File | Công dụng |
| --- | --- |
| `FERNIMOON-STUDIO.mp4` | Video hoàn thiện, có phụ đề động sẵn trong hình |
| `captions.srt` | Phụ đề rời theo cụm từ |
| `captions.ass` | Phụ đề với animation và thương hiệu |
| `script.json` | Kịch bản, lời đọc và truy vấn tìm video từng cảnh |
| `sources.json` | ID, URL trang nguồn, tác giả, truy vấn và liên kết giấy phép Pixabay |
| `timing.json` | Mốc thời gian từng từ, cảnh và tỷ lệ tempo đã dùng |
| `manifest.json` | Chủ đề, model, voice ID và thông số video đã kiểm tra |
| `upload.txt` | Tiêu đề và mô tả tiếng Anh để đăng Shorts |

Hệ thống **tạo file để bạn tải xuống**, chưa tự đăng lên YouTube. Không yêu cầu YouTube OAuth. Các video đang chạy được xếp hàng; không hủy một lần chạy đang trả phí TTS để bắt đầu lần mới. GitHub concurrency chỉ giữ một lần chạy hoạt động và một lần chờ; tránh gửi nhiều chủ đề cùng lúc nếu muốn giữ tất cả.

## Kiểm tra khớp tư liệu lịch sử (nâng cấp sau video #9)

Video #9 dùng một số clip Pixabay không liên quan trực tiếp tới lời kể, như đền chùa Kyoto/Osaka và thành phố Thượng Hải cho sự kiện Chiến tranh Việt Nam. Đó là footage stock minh họa, **không phải tài liệu lưu trữ lịch sử**.

Trong chế độ `history`, hệ thống nay kiểm tra **tên địa điểm và nhãn nội dung (tags) của từng clip trước khi tải**. Nếu một video bị gắn nhãn ở quốc gia khác với bối cảnh đang kể, hoặc chỉ trùng từ chung chung mà không có chủ thể phù hợp, sẽ không được chọn. Các lỗi đối tượng rõ ràng như máy quay đĩa than thay máy ghi băng cũng bị loại. Khi có nhiều lựa chọn, độ khớp nội dung được ưu tiên hơn tỷ lệ khung hình. `sources.json` ghi `visual_review` và `authenticity: stock_illustration_not_verified_archive`.

**Giới hạn không được che giấu:** Đây chỉ là kiểm tra metadata Pixabay, chưa có thị giác AI xem từng clip, chưa có hệ thống tìm/chứng minh nguồn tư liệu gốc hoặc kiểm tra thực địa. Metadata người tải lên có thể thiếu hoặc sai; clip khớp từ khóa vẫn có thể không đúng thời kỳ. Không bao giờ mô tả footage stock là phim tư liệu thật của sự kiện. Nếu không tìm được clip phù hợp, pipeline báo lỗi **trước khi gọi ElevenLabs** thay vì dựng một video gây hiểu lầm. Muốn có phim/ảnh lưu trữ đích thực phải tích hợp nguồn archival có quyền sử dụng rõ ràng và kiểm duyệt bằng con người hoặc mô hình thị giác.

## Tư liệu thật trước, minh họa sau; khoảng ngắt âm thanh (v3)

FERNIMOON ưu tiên từng cảnh theo đúng thứ tự:

1. **Wikimedia Commons:** tìm video/ảnh chụp đúng nhân vật, địa điểm, vật thể hoặc sự kiện bằng 1–2 truy vấn `archive_queries` do Gemini tạo. Chỉ tải các định dạng FFmpeg đọc được và file có metadata giấy phép **Public Domain / CC0**. Tư liệu vẫn phải kiểm tra thủ công: metadata hợp lệ **không chứng minh** phim/ảnh được quay đúng thời điểm lịch sử.
2. **Pixabay Videos:** nếu không tìm được ảnh hoặc video Commons đủ liên quan, chọn footage quay thật có tags mô tả phù hợp. Trong chế độ lịch sử không dùng clip sai quốc gia hay sai chủ thể. Video stock hiện đại không được coi là tư liệu lưu trữ của sự kiện.
3. **Minh họa:** chỉ khi hai tầng trên không có nguồn thích hợp, thử tìm ảnh vẽ/tranh minh họa công khai có giấy phép trên Commons. Cảnh này hiện chữ **ILLUSTRATION** trong video. Nếu cả ba tầng không đủ nguồn, pipeline dừng trước khi gọi ElevenLabs, không tự lấy nội dung không liên quan.

**Âm thanh tạo điểm nhấn:** Gemini có thể đề xuất **một sound cue dài 1–2 giây**, ví dụ tiếng cánh quạt trực thăng hoặc tiếng nhiễu radio. Pipeline chỉ lấy âm thanh thật khi Commons có bản thu với metadata Public Domain / CC0, tải và xác nhận có audio hợp lệ. Nếu tìm được và giọng đọc có đủ khoảng hở giữa hai cảnh, FFmpeg tách lời dẫn thành hai phần, chèn âm thanh vào chính giữa **không có lời đọc đè lên**, đồng bộ chuyển cảnh và phụ đề. Tỷ lệ thời gian giữ tổng 35–45 giây. Khi không có file hoặc không có khoảng hở thích hợp, **không chèn khoảng lặng giả**.

`sources.json` lưu nguồn, tác giả, giấy phép, mức ưu tiên, tính xác thực chưa kiểm chứng; `upload.txt` có danh sách nguồn để đưa vào phần mô tả. Nếu có sound cue, `sound_source.json` cho biết tên file, người tạo, trang gốc và giấy phép.

**Giới hạn:** đây là cơ chế tìm kiếm bằng từ khóa/metadata, chưa có mô hình nhận diện hình ảnh kiểm chứng từng frame hay dịch vụ xác minh sử liệu. Kho lưu trữ có thể không trả về kết quả cho một chủ đề hiếm. Bộ lọc bản quyền bảo thủ sẽ bỏ qua nhiều ảnh CC BY / CC BY-SA nếu chưa có công cụ đáp ứng đầy đủ điều kiện cấp phép. Đây là giới hạn có chủ đích để tránh sử dụng sai quyền nội dung.

## Tư liệu thật và tính chính xác

- Chỉ tải MP4 từ CDN của Pixabay, chỉ nhận kết quả loại `film`; loại các clip có nhãn/tag AI, CGI, animation, 3D, minh họa. Không thay thế video thiếu bằng ảnh AI.
- **Metadata do người tải lên cung cấp, nên bộ lọc không thể chứng minh tuyệt đối video chưa bị tạo/chỉnh sửa bằng AI.** Xem lại `sources.json` và trang nguồn trước khi đăng. Các API không xác minh tính chân thực của cảnh quay.
- Video tư liệu minh họa chủ đề, không phải bằng chứng của sự kiện cụ thể. Gemini được hướng dẫn tránh bịa số liệu/tin mới, nhưng chưa có bước kiểm chứng nguồn tin trực tiếp. Kiểm tra sự thật trước khi đăng, đặc biệt với nội dung thời sự.
- Tuân thủ [Pixabay Content License](https://pixabay.com/service/license-summary/) và quyền liên quan đến người, thương hiệu, địa điểm trong clip. Mỗi video kèm danh sách nguồn để kiểm tra.
- Video ngang được crop giữa để lấp đầy khung dọc; cần xem lại chủ thể có bị cắt không. Clip ngắn có thể được lặp để phủ đủ cảnh. Không thêm nhạc nền có bản quyền; chỉ sử dụng lời đọc ElevenLabs.
- Lưu cache kết quả tìm kiếm 24 giờ theo hướng dẫn Pixabay. Cache không chứa API key; workflow phục hồi cache giữa các lần chạy.

### Khi Pixabay không tải được một clip

- Log tải video chỉ ghi mã HTTP, host CDN đã được kiểm tra, ID clip, cảnh và số lần thử. Không ghi URL đầy đủ, query string/chữ ký, API key, response body hoặc lỗi mạng thô.
- Mỗi URL được tải tối đa **3 lần** khi gặp HTTP **408, 429, 5xx**, lỗi kết nối, timeout hoặc dữ liệu tải thiếu. Thời gian chờ tăng dần; ưu tiên `Retry-After` nếu có, giới hạn **30 giây**. Mỗi thao tác mạng có timeout 30 giây. File `.part` được xóa trước lần thử tiếp theo; chỉ thay file đích sau khi tải xong.
- HTTP **401/403/404/410 từ CDN** có thể do URL hết hạn, clip bị gỡ hoặc hạn chế truy cập. Hệ thống làm mới kết quả Pixabay tối đa **một lần cho mỗi truy vấn trong một lần chạy**, bỏ cache cũ ngay cả khi chưa đủ 24 giờ. Chỉ thử lại cùng clip nếu API trả về URL khác và metadata vẫn qua kiểm tra nguồn; không lặp URL đã thất bại hoặc tìm cách vượt hạn chế CDN.
- Nếu clip vẫn lỗi, chọn clip `film` khác; tối đa **3 ID clip cho mỗi truy vấn**, rồi chuyển sang truy vấn thay thế của cảnh. Clip lỗi và clip đã dùng không được chọn lại trong các cảnh sau. `sources.json` chỉ chứa clip tải thành công, bao gồm URL mới nếu được làm mới.
- Giữ nguyên kiểm tra HTTPS/host MP4 Pixabay ở URL ban đầu, từng redirect và URL cuối; giới hạn 150 MiB, loại video và nhãn AI. Phản hồi HTML thay vì MP4 bị từ chối. Lỗi chính sách nguồn hoặc ghi file cục bộ dừng pipeline, không bị che thành lỗi mạng.
- Run [42184840403](https://github.com/bacuabesua1997-coder/fernimoon-shorts./actions/runs/42184840403) dừng ở lần tải đầu tiên sau khi Gemini hoàn tất và không có cache phục hồi. Log cũ không giữ mã HTTP nên chưa thể xác định nguyên nhân CDN cụ thể; thông báo mới giúp phân biệt những trường hợp trên.

## Chạy trên máy hoặc Codex

Yêu cầu Python 3.12+, FFmpeg/ffprobe có `libass`, `libx264`, `atempo`, `loudnorm` và font DejaVu Sans.

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y python3 ffmpeg fonts-dejavu-core

# Đứng tại thư mục gốc repository.
# Thiết lập bốn biến môi trường tương ứng Secrets bằng cơ chế quản lý bí mật của bạn.
python3 -m fernimoon --topic "Why sea turtles cross entire oceans" --duration 40
```

CLI đọc biến môi trường, **không tự đọc `.env` của pipeline cũ**. Kết quả nằm trong `output/fernimoon/short-<ID>/delivery/`. Mỗi lần chạy dùng thư mục riêng để tránh lấy nhầm MP4 từ lần trước. File tạm/narration/clip gốc ở thư mục cha; trên Actions chỉ thư mục `delivery` được tải lên. Toàn bộ `output/` đã được `.gitignore` gốc bỏ qua.

Không cần `pip install`, `npm install` hoặc sửa `package.json` để chạy bộ tạo mới.

## Kiểm thử

```bash
# Unit tests: HTTP giả lập, không gọi API, không cần key
python3 -m unittest discover -s fernimoon/tests -v

# Kiểm thử toàn tuyến dựng video: FFmpeg thật, 1080x1920, 40 giây
FERNIMOON_RENDER_TEST=1 python3 -m unittest discover -s fernimoon/tests -v

# Kiểm thử dự án TypeScript gốc nếu cần
npm ci
npm test
npm run typecheck
```

Smoke test sử dụng video test pattern có chuyển động và âm thử tổng hợp làm fixture, **không phải video thành phẩm để đăng**, không gọi Gemini/Pixabay/ElevenLabs và không tính phí. Test kiểm tra file MP4 thực tế, phụ đề, metadata và Artifact package. Workflow **FERNIMOON STUDIO - Tests** chạy unit tests + smoke test khi có thay đổi liên quan; không dùng Secrets trên pull request.

Các kiểm thử không thay thế một lần chạy với key thật: quyền tài khoản, giọng đọc, quota, chất lượng footage và model cần được kiểm tra trong lần tạo Short đầu tiên.

## Xử lý lỗi thường gặp

| Thông báo | Cách xử lý |
| --- | --- |
| Không thấy Run workflow | Merge workflow vào `main`, bật Actions, đăng nhập tài khoản có quyền chạy; thử trình duyệt Desktop site |
| Missing GitHub Secrets | Thêm đủ bốn Repository Secrets, kiểm tra đúng chữ hoa và không để trống |
| HTTP 401/403 từ API | Kiểm tra key, quyền API/model và quyền dùng voice; không dán key vào issue |
| HTTP 401/403/404/410 từ Pixabay CDN | Hệ thống tự làm mới URL một lần/truy vấn và thử clip khác; nếu mọi clip đều lỗi, có thể do clip bị gỡ hoặc CDN hạn chế truy cập, không nhất thiết do API key |
| No downloadable real-film candidate | Đã hết số clip được phép thử; xem mã HTTP và ID clip trong log, thử lại sau hoặc chọn chủ đề khác |
| HTTP 429 | Kiểm tra quota/số dư; đợi rồi chạy lại. Gemini/Pixabay có retry giới hạn |
| No suitable real-film candidate | Dùng chủ đề có cảnh quay thực tế phổ biến hơn, ví dụ rừng, động vật, biển; không có fallback ảnh |
| Missing/mismatched timestamps | ElevenLabs không trả alignment khớp lời đọc; thử voice/model tương thích. Không xuất phụ đề đoán thời gian |
| Narration is too short/long | Thử giọng khác hoặc tạo lại kịch bản. Hệ thống không ép tốc độ quá ±20% hoặc cắt lời đọc |
| Gemini invalid script | Model được thử sửa một lần; nếu vẫn sai, thử chủ đề/model khác |
| FFmpeg timeout/failed | Mở bước dựng để đọc lỗi; clip lỗi hoặc workflow quá thời gian sẽ không tải MP4 chưa kiểm tra |

Một lần chạy thường có 1–2 lần sinh kịch bản (lần thứ hai khi JSON sai), tối đa 2 lần retry mỗi request Gemini/Pixabay khi gặp lỗi tạm thời, và **một request ElevenLabs**. Không tự retry ElevenLabs khi kết nối lỗi để tránh thanh toán lặp không rõ ràng. Chạy lại workflow là một lần tạo mới và có thể phát sinh phí mới.
