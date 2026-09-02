import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../services/auth_service.dart';
import '../../../../services/friend_service.dart';
import '../../../profile/widgets/friends_list_shared.dart';
import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_party.dart';

class BlindMeetingPartyFriendPickerScreen extends StatefulWidget {
  final String partyId;

  const BlindMeetingPartyFriendPickerScreen({super.key, required this.partyId});

  @override
  State<BlindMeetingPartyFriendPickerScreen> createState() =>
      _BlindMeetingPartyFriendPickerScreenState();
}

class _BlindMeetingPartyFriendPickerScreenState
    extends State<BlindMeetingPartyFriendPickerScreen> {
  final _auth = AuthService();
  final _friends = FriendService();
  final _repository = BlindMeetingRepository();

  String? _userId;
  bool _ready = false;
  bool _canRead = false;
  bool _sending = false;
  final Set<String> _selected = {};

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final userId = await _repository.currentUserId();
    final hasSession = userId != null && userId.isNotEmpty
        ? await _auth.ensureCanonicalAppSession()
        : false;
    final canRead =
        hasSession && FirebaseAuth.instance.currentUser?.uid == userId;
    if (!mounted) return;
    setState(() {
      _userId = userId;
      _canRead = canRead;
      _ready = true;
    });
  }

  String _formatDate(DateTime? date) => date == null
      ? '추가일 정보 없음'
      : '${date.year}.${date.month.toString().padLeft(2, '0')}.${date.day.toString().padLeft(2, '0')} 친구가 되었어요';

  Future<void> _send(int remaining) async {
    if (_sending || _selected.isEmpty) return;
    setState(() => _sending = true);
    try {
      for (final userId in _selected.take(remaining)) {
        await _repository.createPartyInvite(
          partyId: widget.partyId,
          inviteeUserId: userId,
        );
      }
      if (!mounted) return;
      HapticFeedback.mediumImpact();
      Navigator.of(context).pop();
    } catch (error) {
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('초대하지 못했어요'),
          content: Text(error.toString().replaceFirst('Exception: ', '')),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('확인'),
            ),
          ],
        ),
      );
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FriendsListSharedColors.background,
      appBar: AppBar(
        title: const Text('설레연 친구에서 초대'),
        backgroundColor: FriendsListSharedColors.surface,
        foregroundColor: FriendsListSharedColors.textMain,
        surfaceTintColor: Colors.transparent,
      ),
      body: !_ready
          ? const Center(child: CircularProgressIndicator())
          : !_canRead || _userId == null
          ? const Center(child: Text('학교 이메일 인증이 완료된 계정에서 친구를 초대할 수 있어요.'))
          : StreamBuilder<BlindMeetingParty?>(
              stream: _repository.watchParty(widget.partyId),
              builder: (context, snapshot) {
                if (snapshot.hasError) {
                  return Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: const Text(
                        '팀 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.',
                        textAlign: TextAlign.center,
                      ),
                    ),
                  );
                }
                final party = snapshot.data;
                if (party == null) {
                  return const Center(child: CircularProgressIndicator());
                }
                final remaining = party.remainingInviteSlots;
                final excluded = {
                  ...party.acceptedUserIds,
                  ...party.pendingInviteeIds,
                };
                return Column(
                  children: [
                    Container(
                      width: double.infinity,
                      margin: const EdgeInsets.fromLTRB(20, 12, 20, 4),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: FriendsListSharedColors.surface,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: FriendsListSharedColors.line),
                      ),
                      child: Text(
                        '설레연 친구 목록에서 최대 $remaining명을 선택하세요.\n초대를 받은 친구가 수락하면 같은 팀에 바로 들어와요.',
                        style: const TextStyle(
                          color: FriendsListSharedColors.textSub,
                          height: 1.45,
                        ),
                      ),
                    ),
                    Expanded(
                      child: FriendsListStreamBody(
                        currentUserId: _userId!,
                        friendService: _friends,
                        mode: FriendsListStreamMode.picker,
                        excludedFriendUserIds: excluded,
                        selectedFriendUserIds: _selected,
                        formatAddedAt: _formatDate,
                        pickerMaxAdditionalSelections: remaining,
                        pickerSelectedCount: _selected.length,
                        onPickerToggle: (item, select) {
                          HapticFeedback.selectionClick();
                          setState(() {
                            if (select && _selected.length < remaining) {
                              _selected.add(item.friendUserId);
                            } else if (!select) {
                              _selected.remove(item.friendUserId);
                            }
                          });
                        },
                      ),
                    ),
                    SafeArea(
                      top: false,
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: FilledButton(
                          onPressed:
                              _selected.isEmpty || _sending || remaining == 0
                              ? null
                              : () => _send(remaining),
                          style: FilledButton.styleFrom(
                            minimumSize: const Size.fromHeight(52),
                            backgroundColor: FriendsListSharedColors.primary,
                          ),
                          child: _sending
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : Text(
                                  _selected.isEmpty
                                      ? '친구를 선택해주세요'
                                      : '선택한 ${_selected.length}명에게 팀 초대 보내기',
                                ),
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
    );
  }
}
