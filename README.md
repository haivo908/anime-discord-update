# Anime Update miễn phí cho Discord

Bộ công cụ đã cấu hình hai phim bạn chọn. Chạy trên GitHub Actions theo lịch 30 phút, kể cả khi PC của bạn tắt. Không cần mời bot vào Discord.

**Trạng thái bàn giao:** đã kiểm tra logic đọc tập/chống trùng bằng dữ liệu mẫu theo cấu trúc trang quan sát được. Chưa triển khai lên GitHub, chưa thử truy cập từ máy chủ GitHub và chưa gửi vào Discord của bạn. Đọc được bằng trình duyệt tại máy bạn không đảm bảo đọc được từ máy chủ GitHub.

## 1. Tạo kho trên GitHub

Đăng nhập GitHub, tạo repository mới tên `anime-discord-update`. Chọn **Public** nếu muốn dùng standard GitHub Actions miễn phí mà không phụ thuộc hạn mức phút của kho riêng tư. Danh sách phim và lịch sử thông báo sẽ công khai; URL webhook phải nằm trong Secret.

Giải nén bộ công cụ. Đưa **nội dung bên trong** thư mục `anime-discord-free` lên gốc repository: `monitor.py`, `anime.json`, `README.md`, `data/state.json`, `.gitignore` và `.github/workflows/anime.yml`.

Nếu tải file qua giao diện GitHub không đưa được thư mục `.github` lên: dùng **Add file → Create new file**, nhập tên `.github/workflows/anime.yml`, mở file cùng tên trong bộ công cụ và dán nguyên nội dung. Các file còn lại có thể dùng **Upload files**. Không chỉ tải nguyên file ZIP lên GitHub vì workflow sẽ không chạy.

## 2. Thử truy cập website trước

Vào **Actions → Anime Update → Run workflow**, chọn `check`, rồi chạy. Bước này chưa cần webhook, không gửi tin và không thay đổi mốc tập.

Mở kết quả chạy. Thành công khi cả hai phim đều có dòng “đọc được tập” và job màu xanh. Nếu gặp HTTP 403, xác minh khu vực hoặc không đọc được mục Tập mới, dừng ở đây: GitHub chưa dùng được cho nguồn này. Việc thêm webhook không sửa được lỗi truy cập. Cần nguồn RSS/API được phép truy cập hoặc máy chủ truy cập được AnimeVietsub, có thể phải đặt tại Việt Nam. Công cụ không tự vượt xác minh hay CAPTCHA.

## 3. Kết nối kênh Discord

Discord: **Cài đặt máy chủ → Tích hợp / Integrations → Webhooks → tạo webhook**. Chọn kênh `#update-anime`, đặt tên `Anime Update`, sao chép URL.

GitHub repository: **Settings → Secrets and variables → Actions → Secrets → New repository secret**:

- Name: `DISCORD_WEBHOOK_URL`
- Secret: dán URL webhook từ Discord.

Giữ URL trong Secret. Không dán vào `anime.json`, `monitor.py`, README, issue hoặc tin nhắn công khai.

## 4. Ghi nhận mốc ban đầu và thử gửi

Chạy **Actions → Anime Update → Run workflow → initialize**. Nếu cả hai nguồn đọc được, công cụ gửi đúng một tin “✅ Đã kết nối Anime Update” kèm tập hiện có. Các tập đã có tại lúc khởi tạo được ghi nhận làm mốc; không đăng lại toàn bộ tập cũ.

Chỉ tiếp tục khi tin xuất hiện trong đúng kênh Discord **và** toàn bộ job GitHub màu xanh, bao gồm bước **Save delivered episodes**. Nếu bước lưu lỗi, kiểm tra **Settings → Actions → General → Workflow permissions** và quyền ghi kho. Rule bảo vệ nhánh cũng có thể chặn việc lưu.

Chạy lại `initialize` không xóa mốc/lịch sử đã có, nhưng gửi lại tin kết nối. Khi thêm phim vào `anime.json`, chạy `initialize` để ghi mốc cho phim mới.

## 5. Bật kiểm tra tự động

GitHub: **Settings → Secrets and variables → Actions → Variables → New repository variable**:

- Name: `ANIME_ENABLED`
- Value: `true`

Từ đó workflow kiểm tra hai phim theo lịch mỗi 30 phút (phút 07 và 37 mỗi giờ). Khi có liên kết tập mới, công cụ đăng thẻ thông báo gồm tên phim, phần, số tập và link của tập.

Muốn tạm dừng: đổi `ANIME_ENABLED` thành `false`. Muốn kiểm tra ngay: chạy thủ công chế độ `notify`.

## Giới hạn cần biết

- Đây là kiểm tra định kỳ, không phải website đẩy thông báo tức thời. GitHub có thể trì hoãn/bỏ lượt chạy khi quá tải; 30 phút là lịch dự kiến, không phải cam kết thời gian nhận tin.
- Công cụ chỉ đọc liên kết số tập trong mục **Tập mới** của đúng trang phim, không suy từ tiêu đề, keywords hoặc lịch phát sóng. Không kiểm chứng video phát được, nội dung phụ đề hay toàn bộ tập cũ.
- Nếu công cụ ngừng lâu và một số tập đã biến mất khỏi mục Tập mới trước khi đọc được, những tập đó có thể không được thông báo.
- Website đổi tên miền, cấu trúc HTML hoặc yêu cầu xác minh thì cần điều chỉnh. Lỗi nguồn giữ nguyên lịch sử gửi và làm job báo lỗi để bạn thấy được vấn đề.
- Giữ `data/state.json` để hạn chế gửi trùng. Tin được ghi nhận sau khi Discord xác nhận nhận tin. Nếu tin đã gửi nhưng quá trình lưu lên GitHub thất bại, lần sau có thể gửi trùng; cần kiểm tra job lỗi trước khi chạy lại.
- Kho công khai không có hoạt động trong 60 ngày có thể bị GitHub tắt lịch chạy; khi đó vào Actions bật lại. Theo dõi các thông báo lỗi workflow của GitHub.
- Không xóa state hoặc khởi tạo lại mốc nếu muốn giữ lịch sử. Việc đổi mã phim cần ghi mốc cho mã mới.

## Nguồn hướng dẫn

- [GitHub: standard runners miễn phí cho kho công khai](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub: lịch chạy, độ trễ và giới hạn 60 ngày](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Discord: tạo webhook](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks)
