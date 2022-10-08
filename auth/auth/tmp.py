# root_account = app.db[User.__name__].find_one({"uuid": ROOT_UUID})
# if root_account is None:
#     app.db[User.__name__].insert_one(
#         to_json(User(uuid=ROOT_UUID, full_name="root"))
#     )


# new_request = request.app.database["requests"].insert_one(to_json(mm_request))
# return {"id": new_request.inserted_id}
