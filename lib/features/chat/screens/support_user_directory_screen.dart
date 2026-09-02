import 'package:flutter/cupertino.dart';

import '../../../router/route_names.dart';
import '../models/chat_room_data.dart';
import '../services/support_chat_service.dart';

class SupportUserDirectoryScreen extends StatefulWidget {
  const SupportUserDirectoryScreen({super.key});

  @override
  State<SupportUserDirectoryScreen> createState() =>
      _SupportUserDirectoryScreenState();
}

class _SupportUserDirectoryScreenState
    extends State<SupportUserDirectoryScreen> {
  final SupportChatService _service = SupportChatService();
  final TextEditingController _searchController = TextEditingController();
  List<SupportUserSummary> _users = const [];
  bool _loading = true;
  bool _loadingMore = false;
  String? _error;
  String? _nextPageToken;

  @override
  void initState() {
    super.initState();
    _loadUsers();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadUsers({bool append = false}) async {
    setState(() {
      if (append) {
        _loadingMore = true;
      } else {
        _loading = true;
      }
      _error = null;
    });
    try {
      final page = await _service.listUsers(
        search: _searchController.text,
        pageToken: append ? _nextPageToken : null,
      );
      if (mounted) {
        setState(() {
          _users = append ? [..._users, ...page.users] : page.users;
          _nextPageToken = page.nextPageToken;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _error = '사용자 목록을 불러오지 못했어요.');
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _loadingMore = false;
        });
      }
    }
  }

  Future<void> _openChat(SupportUserSummary user) async {
    try {
      final roomId = await _service.openSupportChat(user.userId);
      if (!mounted) return;
      await Navigator.of(context, rootNavigator: true).pushNamed(
        RouteNames.chatRoom,
        arguments: ChatRoomData(
          chatRoomId: roomId,
          partnerId: user.userId,
          partnerName: user.nickname,
          partnerUniversity: user.university,
          partnerAvatarUrl: user.avatarUrl,
        ),
      );
    } catch (_) {
      if (!mounted) return;
      await showCupertinoDialog<void>(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('채팅을 열 수 없어요'),
          content: const Text('잠시 후 다시 시도해주세요.'),
          actions: [
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.pop(context),
              child: const Text('확인'),
            ),
          ],
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        middle: const Text('사용자 목록'),
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: _loadUsers,
          child: const Icon(CupertinoIcons.refresh),
        ),
      ),
      child: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
              child: CupertinoSearchTextField(
                controller: _searchController,
                placeholder: '이름으로 검색',
                onSubmitted: (_) => _loadUsers(),
              ),
            ),
            Expanded(
              child: _loading
                  ? const Center(child: CupertinoActivityIndicator())
                  : _error != null
                  ? Center(child: Text(_error!))
                  : _users.isEmpty
                  ? const Center(child: Text('표시할 사용자가 없어요.'))
                  : ListView.separated(
                      itemCount:
                          _users.length + (_nextPageToken == null ? 0 : 1),
                      separatorBuilder: (_, _) => const SizedBox(height: 1),
                      itemBuilder: (context, index) {
                        if (index == _users.length) {
                          return CupertinoButton(
                            onPressed: _loadingMore
                                ? null
                                : () => _loadUsers(append: true),
                            child: _loadingMore
                                ? const CupertinoActivityIndicator()
                                : const Text('더 보기'),
                          );
                        }
                        final user = _users[index];
                        return CupertinoListTile(
                          title: Text(user.nickname),
                          subtitle: user.university.isEmpty
                              ? null
                              : Text(user.university),
                          trailing: const CupertinoListTileChevron(),
                          onTap: () => _openChat(user),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
