#pragma once

#include "esphome/core/defines.h"
#ifdef USE_API
#include "esphome/core/component.h"
#include "esphome/core/component_iterator.h"
#include "esphome/core/controller.h"
namespace esphome::api {

class APIConnection;

// Macro for generating InitialStateIterator handlers.
// Queues an unavailable status before the entity's normal state.
#define INITIAL_STATE_HANDLER(entity_type, EntityClass, upper) \
  bool InitialStateIterator::on_##entity_type(EntityClass *entity) { /* NOLINT(bugprone-macro-parentheses) */ \
    if (!entity->is_available() && !this->client_->send_entity_availability_state(entity, enums::ENTITY_TYPE_##upper)) \
      return false; \
    return this->client_->send_##entity_type##_state(entity); \
  }

class InitialStateIterator final : public ComponentIterator {
 public:
  InitialStateIterator(APIConnection *client);
#ifdef USE_DEVICES
  bool on_begin() override;
#endif

// Entity overrides (generated from entity_types.h). Stateful entities are implemented via
// INITIAL_STATE_HANDLER. Stateless entities and event are implemented separately.
// NOLINTBEGIN(bugprone-macro-parentheses)
#define ENTITY_TYPE_(type, singular, plural, count, upper) bool on_##singular(type *entity) override;
#define ENTITY_CONTROLLER_TYPE_(type, singular, plural, count, upper, callback) \
  bool on_##singular(type *entity) override;
#include "esphome/core/entity_types.h"
#undef ENTITY_TYPE_
#undef ENTITY_CONTROLLER_TYPE_
  // NOLINTEND(bugprone-macro-parentheses)
#ifdef USE_CAMERA
  bool on_camera(camera::Camera *camera) override;
#endif

 protected:
  APIConnection *client_;
};

}  // namespace esphome::api
#endif
