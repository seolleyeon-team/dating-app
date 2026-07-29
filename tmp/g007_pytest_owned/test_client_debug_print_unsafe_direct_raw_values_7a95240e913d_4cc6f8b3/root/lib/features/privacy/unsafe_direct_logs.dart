
void logUnsafe({
  required dynamic error,
  required StackTrace stack,
  required Map<String, dynamic> request,
}) {
  print(error);
  debugPrint(stack.toString());
  print(request['url']);
}
