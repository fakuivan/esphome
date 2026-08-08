#include "esphome/core/controller.h"
#include "esphome/core/controller_registry.h"
#include "esphome/core/entity_base.h"

#include <gtest/gtest.h>

namespace esphome::core::testing {

class EntityAvailabilityController final : public Controller {
 public:
  void on_entity_availability_update(EntityBase *entity) override {
    this->last_entity = entity;
    this->update_count++;
  }

  EntityBase *last_entity{nullptr};
  int update_count{0};
};

TEST(EntityBase, AvailabilityDefaultsToTrueAndNotifiesOnlyOnChange) {
  static EntityAvailabilityController controller;
  ControllerRegistry::register_controller(&controller);

  EntityBase entity;
  EXPECT_TRUE(entity.is_available());
  EXPECT_EQ(controller.update_count, 0);

  entity.set_available(false);
  EXPECT_FALSE(entity.is_available());
  EXPECT_EQ(controller.last_entity, &entity);
  EXPECT_EQ(controller.update_count, 1);

  entity.set_available(false);
  EXPECT_EQ(controller.update_count, 1);

  entity.set_available(true);
  EXPECT_TRUE(entity.is_available());
  EXPECT_EQ(controller.last_entity, &entity);
  EXPECT_EQ(controller.update_count, 2);
}

}  // namespace esphome::core::testing
